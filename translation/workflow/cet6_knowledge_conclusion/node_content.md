# 历史题目查询

```sql
SELECT id, question, user_answer, reference_answer
FROM user_answer_sheet
ORDER BY bstudio_create_time DESC
LIMIT {{count}}
```



# 筛选出id

```python
async def main(args: Args) -> Output:
    params = args.params
    search_reasult_list = params["search_result"]
    id_list = [int(result.get("id", -1)) for result in search_reasult_list]
    id_list_filter = [i for i in id_list if i > 0]
    ret: Output = {"id_list": id_list_filter}
    return ret
```



# 内容拼接

```python
from typing import Dict, Any
from collections import OrderedDict

async def main(args) -> Dict[str, Any]:
    params = args.params
    question_list = params["question_list"]
    judgement_list = params["judgement_list"]
    md = []
    for idx, (q_item, j_item) in enumerate(zip(question_list, judgement_list), start=1):
        question = q_item.get("question", "")
        user_answer = q_item.get("user_answer", "")
        reference_answer = q_item.get("reference_answer", "")
        output_list = j_item.get("outputList", [])

        md.append(f"# 练习{idx}\n\n")
        md.append(f"## 1. 题目\n\n{question}\n\n")
        md.append(f"## 2. 用户回答\n\n{user_answer}\n\n")
        md.append(f"## 3. 参考答案\n\n{reference_answer}\n\n")
        md.append("## 4. 点评\n\n")

        if not output_list:
            md.append("（无点评）\n")
            continue

        groups = OrderedDict()
        for item in output_list:
            dim = item.get("dim_name", "未分类")
            if dim not in groups:
                groups[dim] = []
            groups[dim].append(item)

        for j, (dim_name, items) in enumerate(groups.items(), start=1):
            md.append(f"### 4.{j} {dim_name}\n\n")
            md.append("| 错误类型 | 错误描述 | 错误片段 | 修改建议 |\n")
            md.append("| -------- | -------- | -------- | -------- |\n")
            for err in items:
                etype = err.get("error_type", "").strip()
                edesc = err.get("error_description", "").strip()
                epart = err.get("error_part", "").strip()
                advice = err.get("amending_advice", "").strip()
                if not (etype or edesc or epart or advice):
                    continue
                etype = etype.replace("|", "\\|").replace("\n", " ")
                edesc = edesc.replace("|", "\\|").replace("\n", " ")
                epart = epart.replace("|", "\\|").replace("\n", " ")
                advice = advice.replace("|", "\\|").replace("\n", " ")
                md.append(f"| {etype} | {edesc} | {epart} | {advice} |\n")
            md.append("\n")

    return {"output": "".join(md)}
```

