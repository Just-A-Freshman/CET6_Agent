# 生成查询语句

```python
async def main(args: Args) -> Output:
    params = args.params
    question_list = params.get("questions_list", [])
    
    excluded_sentences = [
        item["question"].replace("'", "''") 
        for item in question_list 
        if "question" in item
    ]
    
    if not excluded_sentences:
        sql = "SELECT sentence FROM cet6_chinese_sentences ORDER BY RAND() LIMIT 1"
    else:
        in_clause = ', '.join(f"'{s}'" for s in excluded_sentences)
        sql = f"""
        SELECT sentence 
        FROM cet6_chinese_sentences
        WHERE sentence NOT IN ({in_clause})
        ORDER BY RAND() 
        LIMIT 1
        """
    
    ret: Output = {"sql": sql}
    return ret
```



# 基于考点出题

## 系统提示词

````markdown
## 任务
你是一位严格的六级翻译模拟考官。你需要：
1. 根据结合用户上一题的错误情况出一道能英语六级翻译题目
2. 题目不要求内容的相似性，只要求能充分考察用户薄弱点
3. 对于特殊的专有名词，例如`港珠澳大桥`，你需要直接在该名词的后面用括号标注它的翻译

## 输出要求
直接返回中文题目，例如：
```
随着中国电子商务的蓬勃发展，中国快递业（courier industry）的业务量已连续多年位居全球第一，涌现出了一批具有国际竞争力的快递企业。
```
````



## 用户提示词

````markdown
# 上一道翻译题目
{{last_question}}

# 上一题用户的错误总结
```
{{exam_point}}
```
````

