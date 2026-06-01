import asyncio
import json
from collections import defaultdict
from typing import cast
from runtime import Args
from typings.DecisionTreeClassification.DecisionTreeClassification import Input, Output
from openai import AsyncOpenAI



_SYSTEM_PROMPT = """你是一个严格的错误分类助手。

你会收到：
1. 一组可选的分类选项（每个选项有一个 ID、名称和详细定义）
2. 一批待分类的文本项（通过序号 [0], [1], [2]... 标记）

请逐项判断它最适合归入哪个选项，输出 JSON。

输出格式严格如下：
{"classifications": [{"index": 0, "option_id": <选项ID>}, {"index": 1, "option_id": <选项ID>}, ...]}

注意事项：
- 输出的 option_id 必须来自给定的选项列表
- 每个 index 都必须有且仅有一个 option_id
- 不要跳过任何项"""




def _deep_convert(obj):
    if hasattr(obj, "__dict__") and not isinstance(obj, (str, bytes)):
        # CustomNamespace / SimpleNamespace → dict
        return {k: _deep_convert(v) for k, v in vars(obj).items()}
    elif isinstance(obj, dict):
        return {k: _deep_convert(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_deep_convert(item) for item in obj]
    return obj


def build_tree(nodes: list[dict]) -> dict[int, dict]:
    """将扁平节点列表转为 id->node 字典，并为每个节点注入 children 列表。"""
    tree = {}
    for n in nodes:
        nid = n["iid"]
        tree[nid] = {
            "iid": nid,
            "name": n["name"],
            "parent_id": n.get("parent_id"),
            "definition": n.get("definition", ""),
            "children": [],
        }
    for nid, node in tree.items():
        pid = node["parent_id"]
        if pid != -1 and pid in tree:
            tree[pid]["children"].append(nid)
    return tree


def find_root_ids(tree: dict) -> list[int]:
    roots = [nid for nid, node in tree.items() if node["parent_id"] == -1]
    if not roots:
        raise ValueError("树中没有根节点（所有节点都有 parent_id）")
    return roots


def is_leaf(tree: dict, node_id: int) -> bool:
    return len(tree[node_id]["children"]) == 0


def _build_user_prompt(items: list[str], children: list[dict]) -> str:
    """构造用户消息：选项列表 + 待分类项。"""
    lines = ["## 可选分类选项\n"]
    for c in children:
        lines.append(f"[ID: {c['iid']}] {c['name']} — {c['definition']}")
    lines.append("\n## 待分类项\n")
    for i, item in enumerate(items):
        lines.append(f"[{i}] {item}")
    return "\n".join(lines)


async def _call_llm(
    client: AsyncOpenAI,
    model: str,
    items: list[str],
    children: list[dict],
    logger=None,
) -> dict:
    """调用 LLM 做一轮分类，返回 {index: option_id} 的映射。"""

    if logger:
        logger.info(f"LLM 调用: 分类 {len(items)} 项到 {len(children)} 个选项")

    prompt = _build_user_prompt(items, children)
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        reasoning_effort="high",
        extra_body={
            "thinking": {"type": "enabled"},
        }
    )
    raw = resp.choices[0].message.content
    raw = "" if raw is None else raw
    parsed = json.loads(raw)

    result = {}
    valid_ids = {c["iid"] for c in children}
    for entry in parsed["classifications"]:
        idx = entry["index"]
        oid = entry["option_id"]
        if oid not in valid_ids:
            raise ValueError(f"LLM 返回了无效的 option_id={oid}，有效选项: {valid_ids}")
        result[idx] = oid

    if logger:
        logger.info(f"LLM 分类完成: {result}")
    return result


async def _classify_batch(
    tree: dict,
    parent_id: int,
    items: list[str],
    client: AsyncOpenAI,
    model: str,
    logger=None,
) -> list[dict]:
    children = tree[parent_id]["children"]
    child_nodes = [tree[cid] for cid in children]

    if not child_nodes:
        return [
            {
                "item": item,
                "leaf_id": parent_id,
                "leaf_name": tree[parent_id]["name"],
                "path": [tree[parent_id]["name"]],
            }
            for item in items
        ]

    mapping = await _call_llm(client, model, items, child_nodes, logger)
    groups: dict[int, list[int]] = defaultdict(list)
    for idx, child_id in mapping.items():
        groups[child_id].append(idx)

    results = []
    tasks = []
    for child_id, indices in groups.items():
        group_items = [items[i] for i in indices]
        if is_leaf(tree, child_id):
            for item in group_items:
                results.append({
                    "item": item,
                    "leaf_id": child_id,
                    "leaf_name": tree[child_id]["name"],
                    "path": [tree[child_id]["name"]],
                })
        else:
            tasks.append(
                _classify_batch(tree, child_id, group_items, client, model, logger)
            )

    if logger:
        logger.info(
            f"节点 {tree[parent_id]['name']}: "
            f"{len(results)} 项落到叶子层, "
            f"{len(tasks)} 个分支继续递归"
        )

    if tasks:
        branch_results = await asyncio.gather(*tasks)
        for br in branch_results:
            for r in br:
                r["path"].insert(0, tree[parent_id]["name"])
                results.append(r)
    else:
        for r in results:
            r["path"].insert(0, tree[parent_id]["name"])

    return results


def handler(args: Args[Input]) -> Output:
    logger = args.logger
    params = args.input

    logger.info(f"开始分类: {len(params.items)} 项")

    if not params.tree_data:
        return Output(results=[], error="tree_data 为空")
    if not params.items:
        return Output(results=[], error="items 为空")
    if not params.api_key:
        return Output(results=[], error="api_key 为空")

    api_key = params.api_key
    model = params.model or "deepseek-chat"
    base_url = params.base_url or "https://api.deepseek.com/v1"
    start_node_id = params.start_node_id

    try:
        tree_data: list[dict] = cast("list[dict]", _deep_convert(params.tree_data))
        items: list[str] = cast("list[str]", _deep_convert(params.items))

        tree = build_tree(tree_data)

        async def _run():
            client = AsyncOpenAI(api_key=api_key, base_url=base_url)

            if start_node_id != -1:
                return await _classify_batch(tree, start_node_id, items, client, model, logger)

            root_ids = find_root_ids(tree)
            if len(root_ids) == 1:
                return await _classify_batch(tree, root_ids[0], items, client, model, logger)

            root_nodes = [tree[rid] for rid in root_ids]
            mapping = await _call_llm(client, model, items, root_nodes, logger)
            groups: dict[int, list[int]] = defaultdict(list)
            for idx, rid in mapping.items():
                groups[rid].append(idx)

            tasks = []
            for rid, indices in groups.items():
                group_items = [items[i] for i in indices]
                tasks.append(_classify_batch(tree, rid, group_items, client, model, logger))

            branch_results = await asyncio.gather(*tasks)
            flat = []
            for br in branch_results:
                flat.extend(br)
            return flat

        results = asyncio.run(_run())
        logger.info(f"分类完成: {len(results)} 项")
        return Output(results=results, error="")  # type: ignore[arg-type]

    except Exception as e:
        logger.error(f"分类出错: {str(e)}")
        return Output(results=[], error=str(e))  # type: ignore[arg-type]

