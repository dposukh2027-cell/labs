"""Аналіз журналу: повільні, невдалі й повторні виклики, витрати, кеш.

Запуск із папки pr11:

    python eval/analyze.py                       # logs/app.jsonl, усі розділи
    python eval/analyze.py logs/app.jsonl --since 2026-10-23 --section slow

Читання файлу, відбір за датою і допоміжні функції готові. Розділи
звіту — заготовки: поля, за якими вони працюють, — ваші, бо назви
подій і полів ви обрали, коли писали записи в шлюзі й фонових задачах.
`summary` працює на будь-якому журналі й показує, що в ньому взагалі є.

Орієнтир для кожного розділу — питання, на яке він відповідає; воно в
докстрінгу. Відповідь — числа й кілька рядків журналу, а не переказ.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def load(path: Path, since: str | None = None) -> list[dict]:
    """Прочитати JSON lines. Рядки, які не розбираються, рахуються й
    пропускаються; `since` — дата або час у форматі ISO, від якого брати
    записи (порівнюється з полем `ts` як рядок)."""
    records: list[dict] = []
    broken = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                broken += 1
                continue
            if since and str(record.get("ts", "")) < since:
                continue
            records.append(record)
    if broken:
        print(f"(пропущено рядків, що не розбираються: {broken})", file=sys.stderr)
    return records


def percentile(values: list[float], p: float) -> float | None:
    """p-й процентиль (0 ≤ p ≤ 1) за найближчим рангом; `None` для
    порожнього списку."""
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * p)))
    return ordered[index]


def group(records: list[dict], key: str) -> dict:
    """Згрупувати записи за значенням поля."""
    groups: dict = defaultdict(list)
    for record in records:
        groups[record.get(key)].append(record)
    return groups


def summary(records: list[dict]) -> None:
    """Що взагалі є в журналі: скільки записів, за який час, яких подій і
    рівнів скільки. Працює на будь-якому журналі."""
    if not records:
        print("записів немає")
        return
    stamps = [r.get("ts", "") for r in records]
    print(f"записів: {len(records)}; від {min(stamps)} до {max(stamps)}")
    print("рівні:", dict(Counter(r.get("level") for r in records)))
    print("події:")
    for event, count in Counter(r.get("event") for r in records).most_common():
        print(f"  {count:>6}  {event}")


def slow(records: list[dict]) -> None:
    """Які виклики найповільніші й що таке «повільно» в цих числах?

    Розподіл тривалості звертань до провайдера (медіана, p95, максимум),
    а не середнє; десятка найдовших із ідентифікаторами, провайдером,
    моделлю, спробою; де пройшов час — у черзі, до першого фрагмента чи
    в генерації; розріз за провайдером і годиною.
    """
    attempts = [r for r in records if r.get("event") == "llm.attempt" and
                isinstance(r.get("duration_ms"), (int, float))]
    durations = [float(r["duration_ms"]) for r in attempts]
    if not attempts:
        print("завершених спроб провайдера немає")
        return
    print(f"викликів: {len(durations)}; медіана {percentile(durations, .5):.1f} ms; "
          f"p95 {percentile(durations, .95):.1f} ms; максимум {max(durations):.1f} ms")
    print("найповільніші:")
    for row in sorted(attempts, key=lambda r: r["duration_ms"], reverse=True)[:10]:
        print(f"  {row['duration_ms']:>8.1f} ms draft={row.get('draft_id')} "
              f"request={row.get('request_id')} provider={row.get('provider')} "
              f"model={row.get('model')} attempt={row.get('attempt')} "
              f"queue={row.get('queue_wait_ms')} ms first={row.get('first_token_ms')} ms")
    by_provider = defaultdict(list)
    by_hour = defaultdict(list)
    for row in attempts:
        by_provider[row.get("provider")].append(float(row["duration_ms"]))
        by_hour[str(row.get("ts", ""))[:13]].append(float(row["duration_ms"]))
    print("за провайдером:", {key: {"count": len(values), "p50_ms": percentile(values, .5)}
                              for key, values in by_provider.items()})
    print("за годиною:", {key: {"count": len(values), "p50_ms": percentile(values, .5)}
                          for key, values in by_hour.items()})


def failed(records: list[dict]) -> None:
    """Що й чому не вдалося?

    Невдалі спроби за видом збою; остаточні збої чернеток; частка
    чернеток із невдалою першою спробою, які все ж завершилися успіхом
    (чи окупилися повтори); вартість спроб, які нічого не дали.
    """
    failures = [r for r in records if r.get("event") == "llm.attempt" and r.get("status") == "failed"]
    print("невдалі спроби за видом:", dict(Counter(r.get("kind", "unknown") for r in failures)))
    terminal = [r for r in records if r.get("event") == "draft.failed"]
    print(f"остаточні збої чернеток: {len(terminal)}")
    drafts = {r.get("draft_id"): r for r in records if r.get("event") in {"draft.done", "draft.failed"}}
    attempts_by_draft = defaultdict(list)
    for row in records:
        if row.get("event") == "llm.attempt":
            attempts_by_draft[row.get("draft_id")].append(row)
    first_failed = {draft_id for draft_id, rows in attempts_by_draft.items()
                    if rows and rows[0].get("status") == "failed"}
    recovered = sum(1 for draft_id in first_failed if drafts.get(draft_id, {}).get("event") == "draft.done")
    print(f"першу спробу відновлено: {recovered}/{len(first_failed)}")
    lost_cost = sum(float(r.get("cost") or 0) for r in failures)
    print(f"вартість невдалих спроб: {lost_cost:.6f} $")


def repeated(records: list[dict]) -> None:
    """Що ми робили двічі?

    Той самий ключ кешу кілька разів за короткий час (кандидати на кеш
    і питання «чому»); чернетки з кількома спробами (повтори шлюзу);
    клієнти з серіями замовлень за хвилину.
    """
    by_key = defaultdict(list)
    by_draft = defaultdict(list)
    by_client = defaultdict(list)
    for row in records:
        if row.get("event") == "llm.attempt":
            if row.get("cache_key"):
                by_key[row["cache_key"]].append(row)
            if row.get("draft_id"):
                by_draft[row["draft_id"]].append(row)
        if row.get("event") == "draft.created" and row.get("client_id"):
            by_client[row["client_id"]].append(row)
    repeated_keys = [(key, rows) for key, rows in by_key.items() if len(rows) > 1]
    print(f"повторюваних ключів кешу: {len(repeated_keys)}")
    for key, rows in sorted(repeated_keys, key=lambda item: len(item[1]), reverse=True)[:10]:
        print(f"  {key[:12]}: {len(rows)} викликів, чернетки "
              f"{[row.get('draft_id') for row in rows]}")
    retried = {draft_id: rows for draft_id, rows in by_draft.items() if len(rows) > 1}
    print(f"чернеток із кількома спробами: {len(retried)}")
    for draft_id, rows in retried.items():
        print(f"  {draft_id}: {len(rows)} спроб")
    burst_clients = {client: rows for client, rows in by_client.items() if len(rows) > 1}
    print(f"клієнтів із кількома замовленнями: {len(burst_clients)}")


def spend(records: list[dict]) -> None:
    """Скільки це коштувало?

    Вартість і токени за день, за модель, за клієнта; середня вартість
    чернетки; частка вартості, яка припала на спроби зі збоєм і на
    запасний варіант; скільки записів без вартості або з оцінкою.
    """
    attempts = [r for r in records if r.get("event") == "llm.attempt"]
    if not attempts:
        print("викликів провайдера немає")
        return
    by_day = defaultdict(float)
    by_model = defaultdict(float)
    by_client = defaultdict(float)
    missing = estimated = 0
    for row in attempts:
        cost = row.get("cost")
        if not isinstance(cost, (int, float)):
            missing += 1
            continue
        value = float(cost)
        by_day[str(row.get("ts", ""))[:10]] += value
        by_model[row.get("model", "unknown")] += value
        by_client[row.get("client", "unknown")] += value
        estimated += bool(row.get("cost_estimated"))
    total = sum(by_day.values())
    failed_cost = sum(float(r.get("cost") or 0) for r in attempts if r.get("status") == "failed")
    fallback_cost = sum(float(r.get("cost") or 0) for r in attempts if r.get("fallback"))
    drafts = [r for r in records if r.get("event") == "draft.done" and isinstance(r.get("cost"), (int, float))]
    average = sum(float(r["cost"]) for r in drafts) / len(drafts) if drafts else 0
    print(f"загалом: {total:.6f} $; за день: {dict(sorted(by_day.items()))}")
    print("за моделлю:", {key: round(value, 6) for key, value in by_model.items()})
    print("за клієнтом:", {key: round(value, 6) for key, value in by_client.items()})
    print(f"середня вартість завершеної чернетки: {average:.6f} $; "
          f"невідома для {missing} спроб; оцінена у {estimated} спробах")
    print(f"невдалі спроби: {failed_cost:.6f} $; запасний варіант: {fallback_cost:.6f} $")


def cache_report(records: list[dict]) -> None:
    """Що дав кеш?

    Влучання, промахи, обходи (`fresh`) і частка влучань; скільки
    звертань до провайдера й грошей заощаджено; які звернення
    повторювалися найчастіше.
    """
    hits = [r for r in records if r.get("event") == "llm.cache_hit"]
    misses = [r for r in records if r.get("event") == "llm.cache_miss"]
    bypassed = [r for r in records if r.get("event") == "llm.cache_bypassed"]
    disabled = [r for r in records if r.get("event") == "llm.cache_disabled"]
    total = len(hits) + len(misses)
    print(f"влучання: {len(hits)}; промахи: {len(misses)}; fresh обходи: {len(bypassed)}; "
          f"вимкнено: {len(disabled)}; "
          f"частка влучань: {len(hits) / total:.1%}" if total else
          f"влучання: {len(hits)}; промахи: {len(misses)}; fresh обходи: {len(bypassed)}; "
          f"вимкнено: {len(disabled)}; "
          "частка влучань: —")
    saved = sum(float(row.get("avoided_cost") or 0) for row in hits)
    print(f"викликів провайдера уникнуто: {len(hits)}; збережена вартість за історичною "
          f"вартістю результатів: {saved:.6f} $")
    keys = Counter(row.get("cache_key") for row in misses if row.get("cache_key"))
    print("найчастіші ключі промаху:", keys.most_common(10))


SECTIONS = {
    "summary": summary,
    "slow": slow,
    "failed": failed,
    "repeated": repeated,
    "spend": spend,
    "cache": cache_report,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("log", nargs="?", default="logs/app.jsonl")
    parser.add_argument("--since", help="брати записи від цієї дати/часу (ISO), наприклад 2026-10-23")
    parser.add_argument("--section", choices=["all", *SECTIONS], default="all")
    args = parser.parse_args()

    path = Path(args.log)
    if not path.exists():
        print(f"журналу немає: {path}", file=sys.stderr)
        return 1
    records = load(path, args.since)

    names = list(SECTIONS) if args.section == "all" else [args.section]
    for name in names:
        print(f"\n=== {name}")
        try:
            SECTIONS[name](records)
        except NotImplementedError as exc:
            print(f"(заготовка: {exc})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
