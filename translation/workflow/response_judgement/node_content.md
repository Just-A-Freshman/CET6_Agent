# 初步支持错误_系统提示词

```markdown
# 任务

你是一位严格的六级翻译审校员。你的工作只做一件事：**发现错误并精准描述**。

你会收到：

1. 翻译题目的中文原文
2. 考生据此翻译的英文译文

你需要逐句对比原文和译文，找出译文中存在的所有错误， 宁多勿漏。每发现一个错误，填写四项信息：

| 属性     | 要求                                                         |
| -------- | ------------------------------------------------------------ |
| 编号     | 从1开始，自上往下递增 + 1                                    |
| 错误描述 | 用一句话说清楚错在哪里，让后续审校人员仅凭描述就能理解错误的性质，**无需再看原文或译文**。例：①"漏译了'起源于'这个动词"②"动词时态应用过去时却用了一般现在时"③"直译了中文主谓宾结构，英文表达不自然" |
| 错误片段 | 考生译文中有问题的原文片段，精确到词或短语，**原样摘录**。例："Dragon Boat Festival is in China"中的"is in" |
| 修改建议 | 该片段应改为的正确/更好的表达。例："originates in"           |

# 三个检查方向（按此顺序逐句扫查）

1. 信息完整度：**逐词对照原文和译文**——有没有漏译的词？有没有多译的内容？有没有意思对不上的地方？有没有顺序颠倒了？
2. 语言准确性：**只看译文本身**——时态对吗？主谓一致吗？单复数对吗？介词/冠词用法对吗？句子结构完整吗？
3. 流畅度：如果一个句子信息都对、语法也对，但读起来"不像人话"——太啰嗦？跳跃？搭配奇怪？语体不对？这也算错。

# 重要规则

- **一个错误一条**：如果一个句子或一个措辞中有多个独立错误，不能合并成一条"兼顾"的描述。应拆成两条，每条聚焦一个独立的错误性质。
- **覆盖面尽可能广**：宁可多列也不要遗漏。不确定是否算错的，也列出来
- **不越界**：只做"找出来+描述清楚"。**不评分、不归类、不说这个错误属于哪个维度或哪种类型**
- **不联想**：不要根据错误去推测考生水平或意图，只描述客观事实


# 输出格式
输出格式严格如下：
[{"编号": 1, "错误描述": "XXX", "错误片段": "XXX", "修改建议": "XXX"},  {...}]

若译文没有发现错误，输出空列表：[]
```



# 初步指出错误_用户提示词

```markdown
# 翻译题目
{{String1}}

# 用户的回答
{{String2}}
```



# 错误审核_系统提示词

```markdown
# 任务

你是一位六级翻译错误审核员。你只做一件事：**检查错误列表，剔除误报，给出对应需要删除的编号。**

你会收到：

1. 翻译题目的中文原文
2. 考生的英文译文
3. LLM#1（错误发现AI）输出的错误列表，里面必须包含“编号”列。如果不包含，直接返回空列表。

# 参考LLM#1的判断标准
1. 信息完整度：**逐词对照原文和译文**——有没有漏译的词？有没有多译的内容？有没有意思对不上的地方？有没有顺序颠倒了？
2. 语言准确性：**只看译文本身**——时态对吗？主谓一致吗？单复数对吗？介词/冠词用法对吗？句子结构完整吗？
3. 流畅度：如果一个句子信息都对、语法也对，但读起来"不像人话"——太啰嗦？跳跃？搭配奇怪？语体不对？这也算错。


# 输出格式

你只需要给出数组对象，里面包含被误报的编号，例如：[1, 2, 5]
```



# 错误审核_用户提示词

```markdown
# 翻译题目
{{String1}}

# 用户的回答
{{String2}}

# LLM#1的分析结果
{{String3}}
```



# 删除冗余错误

```python
import json


async def main(args: Args) -> Output:
    params = args.params
    error_conclusion = json.loads(params["error_conclusion"])
    try:
        misinformation_list = [int(i) for i in json.loads(params["misinformation_list"])]
        new_error_conclusion = [i for i in error_conclusion if int(i.get("编号", -1)) not in misinformation_list]
    except json.JSONDecodeError:
        return {"output": error_conclusion}
    
    return {"output": new_error_conclusion}
```



# 拼接信息

```python
import json

async def main(args: Args) -> Output:
    params = args.params
    input = params["input"]
    items = []
    for err in input:
        del err["编号"]  # type:ignore
        items.append(json.dumps(err, ensure_ascii=False))
    ret: Output = {"items": items}
    return ret
```



# 合并错误信息

```python
import json


async def main(args: Args) -> Output:
    params = args.params
    results = params["results"]
    final_error_conclusion = []
    for result in results:
        error_info = json.loads(result["item"])
        dim_name = result["path"][0]
        err_type = result["path"][-1]
        final_error_conclusion.append({**error_info, "维度": dim_name, "错误类型": err_type})
    ret: Output = {"final_err_conclusion": final_error_conclusion}
    return ret
```



# 评分与给出答案

```markdown
# 当前试题
{{String1}}

# 学生给出的译文
{{String2}}

# 上一位老师对学生的错误总结
{{String3}}


```



# 根据错误内容评分_系统提示词

```markdown
你是一名大学英语六级（CET-6）翻译阅卷员。你需要对考生的英文译文进行整体印象评分。

## 输入信息

1. **原文**：待翻译的中文原文
2. **译文**：考生提交的英文译文
3. **错误列表**：前序模块识别出的译文错误

## 评分维度（各 5 分，满分 15 分）

### 信息完整度（5分）
判断译文是否完整、准确地传达了原文的语义内容。
- 5分：内容完整，忠实于原文，无错译漏译
- 4分：核心信息完整，有个别次要信息遗漏或轻微偏差
- 3分：大致达意，但部分信息缺失或误译
- 2分：仅翻译了部分内容，重要信息丢失
- 1分：基本未传达原文内容，或完全不相关

### 语言准确性（5分）
判断译文是否符合英语语法规范，句式运用是否恰当。
- 5分：语法正确，句式结构准确
- 4分：有少量小错误（单复数、冠词等），但不影响理解
- 3分：有较多语法错误，一定程度上影响阅读
- 2分：语法错误普遍，句子结构混乱，难以理解
- 1分：几乎每句都有严重语法错误

### 流畅度（5分）
判断译文是否自然地道，符合英语表达习惯。
- 5分：表达自然地道，用词恰当，无明显翻译痕迹
- 4分：整体流畅，个别表达略显生硬但不影响阅读
- 3分：有明显翻译腔或不自然表达，但尚可理解
- 2分：表达很不自然，多处不符合英语习惯
- 1分：基本不符合英语表达习惯，难读

## 总体参照标准

| 档次 | 总分 | 描述 |
|------|------|------|
| A | 13-15分 | 准确完整、无错译、句式多样、符合英文表达 |
| B | 10-12分 | 完整传达原意、少量小错误、表达基本流畅 |
| C | 7-9分 | 勉强达意、语法用词错误较多、表达生硬 |
| D | 4-6分 | 仅翻译部分内容、逻辑混乱、错误百出 |
| E | 1-3分 | 未作答/完全偏离/仅写无关词汇 |

## 评分方式

1. **整体印象评分**：像真正的阅卷员一样，先通读译文形成整体印象，再分维度打分。不要逐条扣分。
2. **充分参考错误列表**：你需要充分参考原来的错误列表进行评分，但并不是按其数量机械扣分。
3. **关注全局效果**：一个严重的全局错误（如全程时态混乱）比多个局部错误影响更大；相反，多个轻微错误集中在同一处也不应过度扣分。

## 输出

仅输出一个 JSON 对象，不要包含其他内容：
{"信息完整度": <分数>, "语言准确性": <分数>, "流畅度": <分数>}

```



# 总结最小化参考译文_系统提示词

```markdown
# Task
你是一位六级翻译备考老师。你的核心任务是：
基于「当前试题」、「学生给出的译文」和「上一位老师对学生的错误总结」，给出**最小化**改进的参考译文，要求：
- 严格基于当前译文和上一位老师的修改建议
- 禁止引入新表达或扩写
- 禁止使用“……”省略参考译文的任意部分


# 示例输出
你只需要直接将最小化改进的译文输出，同时加粗修改部分内容。禁止输出其他任意说明，例如：
HongKong-Zhuhai-MacauBridge, with a total length of 55 kilometers, is **an** unusual splendid engineering **feat** in **China**.


```



# 获取错误列表

```python
import json

async def main(args: Args) -> Output:
    params = args.params
    try:
        error_conclusion_list = params["input"]
    except json.JSONDecodeError:
        error_conclusion_list = []
    err_list = []
    for item in error_conclusion_list:
        err_list.append(f"{item.get('维度', '')}_{item.get('错误类型', '')}")

    error_string = "','".join(err_list)
    error_string = f"'{error_string}'"
    ret: Output = {"error_list": error_string}
    return ret
```



# 查询用户过去相同错误

```sql
SELECT dim_name, error_type, error_description, error_part, amending_advice
FROM exam_point_record
WHERE CONCAT(dim_name, '_', error_type) IN ({{error_list}})
ORDER BY bstudio_create_time DESC
LIMIT 100;
```



# 总结重现错误

```python
from collections import defaultdict


async def main(args) -> dict:
    def _match_key(e: dict) -> tuple:
        return (e.get("dimension", ""), e.get("error_type", ""))

    def _normalize(errors: list) -> list[dict]:
        key_map = {
            "修改建议": "advice", "amending_advice": "advice",
            "错误类型": "error_type", "error_type": "error_type",
            "维度": "dimension", "dim_name": "dimension",
            "错误片段": "error_part", "error_part": "error_part",
            "错误描述": "error_description", "error_description": "error_description",
        }
        if not errors:
            return []
        out = []
        for e in errors:
            if not isinstance(e, dict):
                continue
            normalized = {}
            for k, v in e.items():
                mapped = key_map.get(k, k)
                if isinstance(v, str):
                    v = v.strip()
                normalized[mapped] = v
            normalized.setdefault("error_type", "")
            normalized.setdefault("error_part", "")
            out.append(normalized)
        return out

    def _get(key, default=None):
        try:
            return params[key] if isinstance(params, dict) else getattr(params, key, default)
        except (KeyError, AttributeError, TypeError):
            return default

    params = args.params
    current_raw = _get("current_error_list") or []
    old_raw = _get("old_error_list") or []

    current = _normalize(current_raw)
    old = _normalize(old_raw)

    past_group: dict[tuple, list[dict]] = defaultdict(list)
    current_group: dict[tuple, list[dict]] = defaultdict(list)

    for e in old:
        past_group[_match_key(e)].append(e)

    for e in current:
        current_group[_match_key(e)].append(e)

    repeated_keys = set(past_group.keys()) & set(current_group.keys())

    repeated = []
    for k in repeated_keys:
        past_errors = past_group[k]
        current_errors = current_group[k]
        total_count = len(past_errors) + len(current_errors)
        if total_count < 3:
            continue

        repeated.append({
            "dimension": k[0],
            "error_type": k[1],
            "total_occurrences": total_count,
            "past": [
                {
                    "error_description": e.get("error_description", ""),
                    "error_part": e.get("error_part", ""),
                    "advice": e.get("advice", ""),
                }
                for e in past_errors
            ],
            "current": [
                {
                    "error_description": e.get("error_description", ""),
                    "error_part": e.get("error_part", ""),
                    "advice": e.get("advice", ""),
                }
                for e in current_errors
            ],
        })

    repeated.sort(key=lambda x: x["total_occurrences"], reverse=True)

    return {"repeated_error_table": repeated}

```



# markdown格式渲染

```python
import json


_DIMENSIONS = ["信息完整度", "语言准确性", "流畅度"]


async def main(args: Args) -> Output:
    params = args.params
    scores = json.loads(params["scores"])
    error_conclusion = params["error_conlusion"]
    repeated_error_table = params["repeated_error_table"]
    user_answer = params["user_answer"]
    reference_answer = params["reference_answer"]
    total = sum(scores.get(d, 0) for d in _DIMENSIONS)
    # 第一部分
    lines = [f"# 1. 总体评价（{total} / 15）"]
    for index, dim in enumerate(_DIMENSIONS, 1):
        score = scores.get(dim, 0)
        dim_errors = [e for e in error_conclusion if e.get("维度") == dim]
        lines.append(f"## 1.{index} {dim}（{score}分）")
        lines.append("")

        if not dim_errors:
            lines.append("> 该维度未发现错误。")
        else:
            lines.append("| 错误类型 | 错误描述 | 错误片段 | 修改建议 |")
            lines.append("|---------|---------|---------|---------|")
            for e in dim_errors:
                etype = e.get("错误类型", "")
                desc = e.get("错误描述", "").replace("|", "\\|")
                snippet = e.get("错误片段", "").replace("|", "\\|")
                suggestion = e.get("修改建议", "").replace("|", "\\|")
                lines.append(f"| {etype} | {desc} | {snippet} | {suggestion} |")

        lines.append("\n---\n")
    # 第二部分
    lines.append("# 2. 重点错误说明")
    repeated_error_table = [] if repeated_error_table is None else repeated_error_table
    if len(repeated_error_table) == 0:
        lines.append("本次练习没有重现过往的错误，再接再厉！")
    else:
        lines.append("下面列举**过去犯的相似错误**，你需要重点留意：")
    for item in repeated_error_table:
        dim = item.get("dimension", "")
        etype = item.get("error_type", "")
        total = item.get("total_occurrences", 0)
        past = item.get("past", [])[:3]
        current = item.get("current", [])
        past_count = len(item.get("past", []))
        current_count = len(current)
        if not past:
            continue

        lines.append(f"## {dim} › {etype}：**共出现 {total} 次**（过去 {past_count} 次，本轮 {current_count} 次）")
        lines.append("| # | 错误描述 | 错误片段 | 修改建议 |")
        lines.append("|---|--------|---------|---------|")
        for i, e in enumerate(past, 1):
            desc = e.get("error_description", "").replace("|", "\\|")
            part = e.get("error_part", "").replace("|", "\\|")
            advice = e.get("advice", "").replace("|", "\\|")
            lines.append(f"| {i} | {desc} | {part} | {advice} |")
        if past_count > 3:
            lines.append(f"|   | *……还有 {past_count - 3} 条同类错误* | | |")
        lines.append("")

        lines.append("---")
        lines.append("")
    
    # 第三部分
    lines.append(f"# 3. 最小化改进的参考译文\n- 用户原译片段：\n\t>“{user_answer}”\n- 最小化改进后：\n\t>“{reference_answer}”")

    ret: Output = {"render_result": "\n".join(lines)}
    return ret
```



# 生成SQL插入语句

```sql
async def main(args):
    records_list = args.params.get('records', [])
    question_id = int(args.params.get('question_id', -1))
    
    if len(records_list) == 0 or question_id == -1:
        return {'sql': ''}
    
    def escape(s):
        return s.replace("'", "''")
    
    values_list = []
    for r in records_list:
        dim_name = escape(str(r.get('维度', ''))).replace("*", "")
        error_type = escape(str(r.get('错误类型', ''))).replace("*", "")
        error_description = escape(str(r.get('错误描述', '')))
        error_part = escape(str(r.get('错误片段', '')))
        amending_advice = escape(str(r.get('修改建议', '')))
        if any(x == "无" for x in (error_type, error_description, error_part, amending_advice)):
            continue
        if not all([dim_name, error_type, error_description, error_part, amending_advice]):
            continue
        values_list.append(f"({question_id}, '{dim_name}', '{error_type}', '{error_description}', '{error_part}', '{amending_advice}')")
    if len(values_list) == 0:
        sql = ""
    else:
        sql = f"""
    INSERT INTO exam_point_record (question_id, dim_name, error_type, error_description, error_part, amending_advice) 
    VALUES {', '.join(values_list)};
    """
    return {'sql': sql}
```



# 计算总得分

```python
import json

async def main(args: Args) -> Output:
    params = args.params
    scores = json.loads(params["scores"])
    ret: Output = {"final_score": sum(scores.values())}
    return ret

```

