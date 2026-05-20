# design-lite.md — X Intelligence MVP 設計メモ

> 「動くパイプライン優先」のため、MVP 段階では本ドキュメントを軽量に保つ。
> 実装が落ち着いたら `docs/requirements.md` / `docs/design.md` / `docs/operations.md` に展開する。

## 1. データフロー

```
keywords.yaml
   │
   ▼
SearchProvider (mock|hermes|xai|x_api) ──► SearchResult
                                            ├ items: [StructuredPost | SearchCitationResult]
                                            ├ capabilities
                                            └ missing_fields
   │
   ▼
dedupe (URL → content-hash)
   │
   ▼
verification.tag_items → VerificationTags (status / source_type / risk_flags)
   │
   ▼
scoring.score_all (profile.yaml → career_relevance ブースト)
   │                       method ∈ {full, engagement_fallback, citation_fallback, llm_only}
   ▼
top_n(N=10)
   │
   ├─► trend_analyzer.analyze_all → [TrendSummary]
   ├─► content_generator.generate_drafts → [ContentDraft] (originality guard)
   └─► video_prompt_generator.generate_video_prompts → [VideoPrompt] (EN+JP)
   │
   ▼
export_results
   ├ daily_reports/YYYY-MM-DD/report.md
   ├ daily_reports/YYYY-MM-DD/run_manifest.json
   ├ csv/YYYY-MM-DD.csv
   ├ excel/YYYY-MM-DD_x_intelligence_report.xlsx (5 sheets)
   ├ content_drafts/YYYY-MM-DD/*.md
   ├ video_prompts/YYYY-MM-DD/*.md
   └ review_queue/YYYY-MM-DD/drafts_to_review.md + buckets
```

## 2. Post モデル

Provider 粒度差を吸収するための Union。

| 種類 | 主用途 Provider | 主要フィールド | 想定欠損 |
|---|---|---|---|
| `StructuredPost` | X API / mock | post_id, author, created_at, text, metrics, url | (full の場合は無し) |
| `SearchCitationResult` | Hermes / xAI x_search | summary, cited_urls, cited_posts, provider_response, confidence | author, created_at, engagement_metrics, thread_context |

両者とも `verification` (status / source_type / risk_flags) と `missing_fields` を必ず持つ。

## 3. Provider Contract

```
SearchProvider.search(query, topic, time_range) -> SearchResult
SearchResult:
    provider_name, query, topic, time_range, retrieved_at
    items: list[Post]
    source_urls: list[str]       # 重複排除済 citation URL
    capabilities: Capabilities   # 8 個の bool フラグ
    missing_fields: list[str]    # 集約済（"engagement_metrics" 等）
    raw_response_path: str|None
```

Capabilities フラグ 8 種:
`supports_raw_post_text`, `supports_author`, `supports_created_at`, `supports_engagement_metrics`, `supports_thread_context`, `supports_citations`, `supports_time_range`, `supports_query_operators`.

## 4. Scoring 設計

5 軸 × 加重で総合スコアを出す。`weights` は `config/output.yaml`。

| 軸 | 計算根拠 | 欠損時 fallback |
|---|---|---|
| importance | log-compressed engagement (likes + 3·reposts + 2·replies + views/50) | citation_count × 2.5 + confidence × 10 |
| novelty | created_at 時差 (6h / 24h / 72h / 7d) | 6.0 (citation は時刻なし) |
| career_relevance | profile.yaml の focus_areas マッチ + target_company hit ブースト | 0 (text 無しなら) |
| note_fit | 文長 + insight 用語ヒット数 | text あり前提 |
| x_fit | 文長 140 字近接度 + パンチ表現ヒット数 | text あり前提 |

`ScoreBreakdown.method` で `full / engagement_fallback / citation_fallback / llm_only` を記録 → manifest で集計できる。

## 5. Verification ルール

- `risk_flags`: rumor / hype / investment_claim / product_claim / pricing_claim / legal_or_policy_claim / security_claim（正規表現ヒューリスティック）
- `verification_status`:
  - `official_source_confirmed` ← source_type=official
  - `multi_source_confirmed` ← citation_count >= 2
  - `single_source` ← founder_executive / engineer_dev / media
  - `needs_manual_check` ← rumor + unknown/influencer
  - その他 → `unverified`

LLM 出力は別経路で `[要事実確認]` マーカーを保守的に付与（mock LLM が既にやっている）。

## 6. Content originality guard

`ContentDraft` の必須フィールド:
`source_urls`, `source_summary`, `my_angle`, `draft_text`, `originality_note`, `needs_review`.

`_too_similar(source, draft) >= 0.80` なら 1 回 retry し、`originality_note` に "regenerated" を記録。
3 チャンネル（x_post / x_thread / linkedin）は draft_text 必須、`note_outline` チャンネルだけ `note_title_candidates` + `note_outline` を追加保持。

## 7. RunManifest

```
{
  run_id, executed_at, provider, llm_provider, config_hash,
  query_count, raw_item_count, deduped_item_count, top10_count,
  warnings, errors, missing_fields_summary, fallback_used
}
```

- LLM API key 未設定で mock に落ちた場合は **必ず** `fallback_used` に `llm:<name>->mock` が入る
- `warnings` は `src/utils/logger.warn()` 経由で buffer に蓄積されたものを `drain_warnings()` で取り出す

## 8. Pattern A / B / C 切替の判断ポイント

- 最初は **Pattern A (mock pure Python)** で UX 全体を確認
- 月数回しか実 API を叩かない予定なら **B (WSL2 Hermes OAuth)**
- 並列実行・自動スケジュール化が要件になったら **C (Remote VPS Hermes)** を検討

## 9. 次の作業（実装後）

- `docs/requirements.md` を実装実態に合わせて書き起こす
- `docs/design.md` で adapter 切替の sequence diagram を起こす
- `docs/operations.md` で日次運用の Runbook を起こす
