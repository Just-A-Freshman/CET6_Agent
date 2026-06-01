from runtime import Args
from typings.repair_json.repair_json import Input, Output
from json_repair import repair_json

def handler(args: Args[Input]) -> Output:
    raw_json = args.input.raw_json

    try:
        repaired = repair_json(raw_json, ensure_ascii=False)
        return Output(
            success=True,
            repaired_json=repaired,
            message="JSON repaired successfully"
        )
    except Exception as e:
        # 修复失败时返回错误信息
        return Output(
            success=False,
            repaired_json="",
            message=f"Repair failed: {str(e)}"
        )