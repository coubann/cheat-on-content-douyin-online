"""自动化复盘报告服务

从已复盘的预测文件中提取数据，生成综合复盘报告：
- 整体预测准确率
- 维度相关性分析
- rubric 演进历史
- 最佳/最差表现内容
- 改进建议

用户数据隔离：predictions 和 reports 路径使用 data/{user_id}/ 子目录。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from backend.app.models.state import CheatState
from backend.app.services.file_io import read_file, safe_write
from backend.app.services.llm import call_llm_json

logger = structlog.get_logger()


async def generate_retro_report(data_dir: Path, user_id: int = 0) -> dict[str, Any]:
    """生成自动化复盘报告

    Pre-conditions:
      - 至少有 1 篇已复盘的预测
    Post-conditions:
      - 返回结构化复盘报告
      - 报告被写入 data/{user_id}/reports/
    Side effects:
      - LLM 调用 (tag="retro_report")
      - 写文件系统
    """
    logger.info("retro_report_start", user_id=user_id)

    # 1. 收集所有已复盘的预测
    retros = _collect_retros(data_dir, user_id=user_id)
    if not retros:
        return {"status": "no_data", "message": "尚无复盘数据，无法生成报告"}

    # 2. 加载 state（系统级根目录）
    state_path = data_dir / ".cheat-state.json"
    state = CheatState.model_validate_json(read_file(state_path))

    # 3. 统计分析
    stats = _compute_stats(retros)

    # 4. 维度相关性分析
    dim_analysis = _analyze_dimensions(retros)

    # 5. rubric 演进历史（系统文件，保持在根目录）
    rubric_history = _extract_rubric_history(data_dir)

    # 6. LLM 综合建议
    llm_insights = await _generate_llm_insights(retros, stats, dim_analysis, state)

    # 7. 组装报告
    report = {
        "status": "ok",
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_retros": len(retros),
            "calibration_samples": state.calibration_samples,
            "rubric_version": state.rubric_version,
            "last_bump_at": state.last_bump_at,
        },
        "accuracy": stats,
        "dimension_analysis": dim_analysis,
        "rubric_history": rubric_history,
        "best_performers": stats.get("top3", []),
        "worst_performers": stats.get("bottom3", []),
        "llm_insights": llm_insights,
    }

    # 8. 写入报告文件
    _save_report(data_dir, user_id=user_id, report=report)

    logger.info("retro_report_complete", total_retros=len(retros), user_id=user_id)
    return report


def _collect_retros(data_dir: Path, user_id: int = 0) -> list[dict[str, Any]]:
    """收集所有已复盘的预测数据

    Pre-conditions:
      - data/{user_id}/predictions/ 目录存在
    Post-conditions:
      - 返回复盘数据列表
    Side effects:
      - 无
    """
    preds_dir = data_dir / str(user_id) / "predictions"
    if not preds_dir.exists():
        return []

    retros: list[dict[str, Any]] = []
    for f in sorted(preds_dir.glob("*.md")):
        content = read_file(f)
        if "## 复盘" not in content:
            continue

        script_id = f.stem

        # 提取维度分
        dims: dict[str, float] = {}
        for dim in ["ER", "HP", "QL", "NA", "AB", "SR", "SAT", "TS", "MS", "CC"]:
            match = re.search(rf"{dim}[：:]\s*(\d+\.?\d*)", content)
            if match:
                dims[dim] = float(match.group(1))

        # 提取 composite
        composite_match = re.search(r"综合分[：:]\s*(\d+\.?\d*)", content)
        composite = float(composite_match.group(1)) if composite_match else 0.0

        # 提取实际数据
        plays_match = re.search(r"播放量[：:]\s*(\d+)", content)
        actual_plays = int(plays_match.group(1)) if plays_match else 0

        likes_match = re.search(r"点赞[：:]\s*(\d+)", content)
        actual_likes = int(likes_match.group(1)) if likes_match else 0

        # 提取预测准确性
        accuracy_match = re.search(r"预测准确性[：:]\s*(\w+)", content)
        accuracy = accuracy_match.group(1) if accuracy_match else "unknown"

        # 提取偏差
        deviation_match = re.search(r"主要偏差[：:]\s*(.+)", content)
        key_deviation = deviation_match.group(1).strip() if deviation_match else ""

        # 提取教训
        lessons = re.findall(r"-\s*(.+)", content.split("### 教训")[1].split("###")[0]) if "### 教训" in content else []

        retros.append({
            "script_id": script_id,
            "dimensions": dims,
            "composite": composite,
            "actual_plays": actual_plays,
            "actual_likes": actual_likes,
            "prediction_accuracy": accuracy,
            "key_deviation": key_deviation,
            "lessons": lessons,
        })

    return retros


def _compute_stats(retros: list[dict[str, Any]]) -> dict[str, Any]:
    """计算预测准确率统计

    Pre-conditions:
      - retros 非空
    Post-conditions:
      - 返回统计信息
    Side effects:
      - 无
    """
    total = len(retros)
    overestimated = sum(1 for r in retros if r["prediction_accuracy"] == "overestimated")
    underestimated = sum(1 for r in retros if r["prediction_accuracy"] == "underestimated")
    accurate = sum(1 for r in retros if r["prediction_accuracy"] == "accurate")

    # 播放量统计
    plays = [r["actual_plays"] for r in retros if r["actual_plays"] > 0]
    avg_plays = sum(plays) / len(plays) if plays else 0
    max_plays = max(plays) if plays else 0
    min_plays = min(plays) if plays else 0

    # 综合分统计
    composites = [r["composite"] for r in retros]
    avg_composite = sum(composites) / len(composites) if composites else 0

    # Top/Bottom 3
    sorted_by_plays = sorted(retros, key=lambda x: x["actual_plays"], reverse=True)
    top3 = [
        {"script_id": r["script_id"], "actual_plays": r["actual_plays"], "composite": r["composite"]}
        for r in sorted_by_plays[:3]
    ]
    bottom3 = [
        {"script_id": r["script_id"], "actual_plays": r["actual_plays"], "composite": r["composite"]}
        for r in sorted_by_plays[-3:]
    ]

    return {
        "total": total,
        "accuracy_distribution": {
            "overestimated": overestimated,
            "underestimated": underestimated,
            "accurate": accurate,
            "unknown": total - overestimated - underestimated - accurate,
        },
        "accuracy_rate": round(accurate / total, 2) if total > 0 else 0,
        "plays": {
            "avg": round(avg_plays),
            "max": max_plays,
            "min": min_plays,
        },
        "composite": {
            "avg": round(avg_composite, 2),
        },
        "top3": top3,
        "bottom3": bottom3,
    }


def _analyze_dimensions(retros: list[dict[str, Any]]) -> dict[str, Any]:
    """分析各维度与实际表现的相关性

    Pre-conditions:
      - retros 非空
    Post-conditions:
      - 返回维度分析结果
    Side effects:
      - 无
    """
    dim_scores: dict[str, list[float]] = {}
    plays_list: list[float] = []

    for r in retros:
        plays_list.append(float(r["actual_plays"]))
        for dim, score in r["dimensions"].items():
            if dim not in dim_scores:
                dim_scores[dim] = []
            dim_scores[dim].append(score)

    if not plays_list or len(plays_list) < 2:
        return {"message": "样本不足，无法计算相关性"}

    # 简单相关性：用维度平均分 vs 播放量排序的一致性
    dim_analysis: dict[str, Any] = {}
    for dim, scores in dim_scores.items():
        if len(scores) < 2:
            continue
        avg_score = sum(scores) / len(scores)
        # 计算与播放量的 Spearman 相关系数（简化版：排序一致性）
        score_ranks = _rank(scores)
        plays_ranks = _rank(plays_list)

        # 只取共同长度
        n = min(len(score_ranks), len(plays_ranks))
        if n < 2:
            continue

        # Spearman 相关系数
        d_squared = sum((score_ranks[i] - plays_ranks[i]) ** 2 for i in range(n))
        spearman = 1 - (6 * d_squared) / (n * (n**2 - 1)) if n > 1 else 0

        dim_analysis[dim] = {
            "avg_score": round(avg_score, 2),
            "correlation_with_plays": round(spearman, 3),
            "sample_count": len(scores),
        }

    # 按相关性排序
    sorted_dims = sorted(
        dim_analysis.items(),
        key=lambda x: abs(x[1]["correlation_with_plays"]),
        reverse=True,
    )

    return {
        "dimensions": dim_analysis,
        "most_predictive": sorted_dims[0][0] if sorted_dims else None,
        "least_predictive": sorted_dims[-1][0] if sorted_dims else None,
    }


def _rank(values: list[float]) -> list[float]:
    """计算排名（处理并列）"""
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n - 1 and indexed[j + 1][1] == indexed[j][1]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def _extract_rubric_history(data_dir: Path) -> list[dict[str, Any]]:
    """从 rubric-memo.md 提取 rubric 演进历史

    该系统文件保持在 data/ 根目录，与用户数据隔离无关。

    Pre-conditions:
      - rubric-memo.md 存在
    Post-conditions:
      - 返回 bump 历史列表
    Side effects:
      - 无
    """
    memo_path = data_dir / "rubric-memo.md"
    if not memo_path.exists():
        return []

    content = read_file(memo_path)

    # 提取 Bump 记录
    history: list[dict[str, Any]] = []
    bump_sections = re.split(r"### Bump 记录", content)
    for section in bump_sections[1:]:  # 跳过第一个（非 bump 部分）
        consistency_match = re.search(r"排序一致性[：:]\s*(\d+\.?\d*)", section)
        pool_match = re.search(r"校准池大小[：:]\s*(\d+)", section)
        date_match = re.search(r"\((\d{4}-\d{2}-\d{2} \d{2}:\d{2})\)", section)

        history.append({
            "date": date_match.group(1) if date_match else "unknown",
            "consistency": float(consistency_match.group(1)) if consistency_match else 0,
            "pool_size": int(pool_match.group(1)) if pool_match else 0,
        })

    return history


async def _generate_llm_insights(
    retros: list[dict[str, Any]],
    stats: dict[str, Any],
    dim_analysis: dict[str, Any],
    state: CheatState,
) -> dict[str, Any]:
    """LLM 生成综合复盘建议

    Pre-conditions:
      - retros 非空
    Post-conditions:
      - 返回 LLM 洞察
    Side effects:
      - LLM 调用 (tag="retro_report")
    """
    retros_summary = "\n".join(
        f"- {r['script_id']}: composite={r['composite']}, "
        f"plays={r['actual_plays']}, accuracy={r['prediction_accuracy']}"
        for r in retros[:10]
    )

    _over = stats['accuracy_distribution']['overestimated']
    _under = stats['accuracy_distribution']['underestimated']
    _accurate = stats['accuracy_distribution']['accurate']

    prompt = f"""基于以下复盘数据，生成综合洞察和建议。

## 复盘数据
{retros_summary}

## 统计
- 总复盘数: {stats['total']}
- 准确率: {stats['accuracy_rate']}
- 高估: {_over}, 低估: {_under}, 准确: {_accurate}
- 平均播放: {stats['plays']['avg']}, 最高: {stats['plays']['max']}

## 维度分析
最预测性维度: {dim_analysis.get('most_predictive', 'N/A')}
最不预测性维度: {dim_analysis.get('least_predictive', 'N/A')}

## 当前 rubric 版本
{state.rubric_version}

返回 JSON：
```json
{{
  "overall_assessment": "整体评估一句话",
  "key_findings": ["发现1", "发现2", "发现3"],
  "rubric_recommendation": "rubric 调整建议",
  "content_strategy": "内容策略建议",
  "next_bump_trigger": "下次 bump 触发条件建议",
  "risk_warnings": ["风险1"]
}}
```"""

    result = await call_llm_json(prompt, tag="retro_report", temperature=0.3)
    return result


async def list_retro_reports(data_dir: Path, user_id: int = 0) -> list[dict[str, Any]]:
    """列出所有历史复盘报告

    Pre-conditions:
      - data/{user_id}/reports/ 目录可能存在或不存在
    Post-conditions:
      - 返回报告摘要列表，按生成时间倒序
    Side effects:
      - 读文件系统
    """
    reports_dir = data_dir / str(user_id) / "reports"
    if not reports_dir.exists():
        return []

    reports: list[dict[str, Any]] = []
    for f in sorted(reports_dir.glob("retro_*.json"), reverse=True):
        try:
            content = read_file(f)
            data = json.loads(content)
            reports.append({
                "report_id": f.stem,
                "generated_at": data.get("generated_at", ""),
                "total_retros": data.get("summary", {}).get("total_retros", 0),
                "accuracy_rate": data.get("accuracy", {}).get("accuracy_rate", 0),
                "rubric_version": data.get("summary", {}).get("rubric_version", ""),
            })
        except (json.JSONDecodeError, KeyError):
            continue

    return reports


async def get_retro_report(data_dir: Path, user_id: int = 0, report_id: str = "") -> dict[str, Any] | None:
    """获取指定历史复盘报告

    Pre-conditions:
      - report_id 格式为 retro_YYYYMMDD_HHMMSS
    Post-conditions:
      - 返回完整报告数据，不存在返回 None
    Side effects:
      - 读文件系统
    """
    report_path = data_dir / str(user_id) / "reports" / f"{report_id}.json"
    if not report_path.exists():
        return None

    try:
        content = read_file(report_path)
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def _save_report(data_dir: Path, user_id: int = 0, report: dict[str, Any] | None = None) -> None:
    """保存报告到文件

    Pre-conditions:
      - report 已生成
    Post-conditions:
      - 报告被写入 data/{user_id}/reports/
    Side effects:
      - 写文件系统
    """
    if report is None:
        report = {}

    reports_dir = data_dir / str(user_id) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"retro_{timestamp}.md"

    # 生成 markdown 报告
    md_content = _format_report_md(report)
    safe_write(report_path, md_content)

    # 同时保存 JSON 版本
    json_path = reports_dir / f"retro_{timestamp}.json"
    safe_write(json_path, json.dumps(report, indent=2, ensure_ascii=False))

    logger.info("retro_report_saved", path=str(report_path), user_id=user_id)


def _format_report_md(report: dict[str, Any]) -> str:
    """将报告格式化为 Markdown"""
    summary = report.get("summary", {})
    accuracy = report.get("accuracy", {})
    dim_analysis = report.get("dimension_analysis", {})
    insights = report.get("llm_insights", {})

    dims_text = ""
    for dim, info in dim_analysis.get("dimensions", {}).items():
        corr = info.get("correlation_with_plays", 0)
        bar = "█" * int(abs(corr) * 20)
        dims_text += f"| {dim} | {info.get('avg_score', 0):.1f} | {corr:+.3f} | {bar} |\n"

    top3_text = "\n".join(
        f"- {p['script_id']}: {p['actual_plays']} 播放 (综合分 {p['composite']})"
        for p in report.get("best_performers", [])
    )
    bottom3_text = "\n".join(
        f"- {p['script_id']}: {p['actual_plays']} 播放 (综合分 {p['composite']})"
        for p in report.get("worst_performers", [])
    )

    findings_text = "\n".join(
        f"- {f}" for f in insights.get("key_findings", [])
    )

    _rubric_history_text = (
        chr(10).join(
            f"- {h['date']}: 一致性={h['consistency']}, 校准池={h['pool_size']}"
            for h in report.get('rubric_history', [])
        )
        or '暂无 bump 记录'
    )

    return f"""# 自动化复盘报告

> 生成时间: {report.get('generated_at', 'N/A')}

## 概览

| 指标 | 值 |
|---|---|
| 总复盘数 | {summary.get('total_retros', 0)} |
| 校准样本数 | {summary.get('calibration_samples', 0)} |
| Rubric 版本 | {summary.get('rubric_version', 'N/A')} |
| 预测准确率 | {accuracy.get('accuracy_rate', 0)} |

## 预测准确性分布

- 高估: {accuracy.get('accuracy_distribution', {}).get('overestimated', 0)}
- 低估: {accuracy.get('accuracy_distribution', {}).get('underestimated', 0)}
- 准确: {accuracy.get('accuracy_distribution', {}).get('accurate', 0)}

## 维度相关性分析

| 维度 | 平均分 | 与播放量相关系数 | 可视化 |
|---|---|---|---|
{dims_text}

- 最预测性维度: {dim_analysis.get('most_predictive', 'N/A')}
- 最不预测性维度: {dim_analysis.get('least_predictive', 'N/A')}

## 最佳表现 Top 3

{top3_text or '暂无数据'}

## 最差表现 Bottom 3

{bottom3_text or '暂无数据'}

## LLM 洞察

**整体评估**: {insights.get('overall_assessment', 'N/A')}

**关键发现**:
{findings_text or '暂无'}

**Rubric 建议**: {insights.get('rubric_recommendation', 'N/A')}

**内容策略**: {insights.get('content_strategy', 'N/A')}

**下次 Bump 触发**: {insights.get('next_bump_trigger', 'N/A')}

## Rubric 演进历史

{_rubric_history_text}
"""
