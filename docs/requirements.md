# requirements.md — X Intelligence & Content Automation Skills

> 本書は output quality polish (commit `5d9898c`) 完了後の **要件凍結版** (2026-05-22 時点)。
> 数値や状態表記は本書作成時点のもので、コード進化とともに更新する。

## 1. 目的

X 上に流れる **AI / テック関連の重要情報** を毎朝効率的に収集し、

- 柴田さん (タイ在住・ハイパースケーラー営業/コンサル転身視野) の **キャリア・事業文脈に直結する切り口** で整理し、
- **note 記事案 / X 投稿案 / X スレッド案 / LinkedIn 投稿案 / 動画・画像プロンプト** まで一気通貫で生成し、
- **Human-in-the-loop レビュー** を前提に、投稿は人間が実行する

ためのローカル MVP。

## 2. スコープ

### 2.1 MVP でできること（本書作成時点）

| 機能 | 状態 | 備考 |
|---|---|---|
| mock data での E2E 実行 | ✅ 実装済 | `--provider mock --llm-provider mock` |
| Claude LLM での要約・ドラフト生成 | ✅ 実装済 | `claude-opus-4-7`、温度パラメータ自動 retry 対応 |
| Hermes Agent (WSL2) 経由の X 検索 | ✅ 実装済 | `hermes -z "<query>" -t x_search`、xAI OAuth Grok 4.3 |
| topic 別 keyword 設定 | ✅ 実装済 | `config/keywords.yaml` の 8 themes |
| Provider Adapter による切替 | ✅ 実装済 | mock / hermes / xai (stub) / x_api (stub) |
| 5 軸スコアリング | ✅ 実装済 | importance / novelty / career_relevance / note_fit / x_fit |
| profile.yaml に基づく柴田さん向け relevance ブースト | ✅ 実装済 | atom-based マッチング、target_company ブースト |
| Verification tagging | ✅ 実装済 | verification_status / source_type / risk_flags |
| Citation 品質シグナル | ✅ 実装済 | manifest + report.md に 🟢🟡🔴 表示 |
| topic-specific prompt override | ✅ 実装済 | grok_xai のみ |
| Content draft (X/X thread/Note outline/LinkedIn) | ✅ 実装済 | originality guard 6 fields |
| Video prompt (note_header / x_short / linkedin_visual / youtube_shorts) | ✅ 実装済 | 静止画/動画で別テンプレ、EN+JP bilingual |
| Markdown / CSV / xlsx 出力 | ✅ 実装済 | xlsx は 5 sheets。openpyxl 未導入時は明示エラーで `pip install -r requirements.txt` を案内 (commit `5d9898c`) |
| Review queue 構造 | ✅ 実装済 | approved / rejected / needs_fact_check |
| Run manifest (再現性 + 品質シグナル) | ✅ 実装済 | config_hash + fixture_hash + citationless_* |
| Secret hygiene | ✅ 実装済 | redact / manifest フィールド検査 / 環境変数非列挙 |
| `--search-fallback {none, mock}` | ✅ 実装済 | 検証/日次運用の切替 |
| 公式アカウント自動 promotion | ✅ 実装済 | `config/official_handles.yaml` 経由で source_type 階層分類 (commit `5d9898c`) |
| Content draft 末尾完結チェック | ✅ 実装済 | 未完結時に `originality_note` に WARNING (commit `5d9898c`) |
| Emerging keywords ノイズ除去 | ✅ 実装済 | URL 断片・一般動詞・純数字を stopword で排除 (commit `5d9898c`) |
| pytest スイート | ✅ 実装済 | 本書作成時点で 138 passed, 1 skipped |

### 2.2 MVP でやらないこと（恒久的な禁止 / 別フェーズ送り）

| 項目 | 状態 | 備考 |
|---|---|---|
| **自動投稿** | ❌ **恒久禁止** | `tests/test_no_auto_posting_capability.py` で常時検証 |
| X API v2 (`tweets/search/recent`) 直叩き | ⏸ 別フェーズ | `src/adapters/search_x_api.py` は stub |
| xAI Responses + x_search 直叩き (Hermes 経由しない) | ⏸ 別フェーズ | `src/adapters/search_xai.py` は stub |
| Grok Imagine 画像/動画の実 API 投入 | ⏸ 別フェーズ | 現在は prompt 生成までで停止 |
| 自動スケジューリング (scheduled-tasks) | ⏸ 別フェーズ | 現在は手動実行 |
| Streamlit レビュー UI | ⏸ 別フェーズ | 現在はファイル移動による review |
| Windows native での Hermes CLI | ⏸ 範囲外 | WSL2 (Pattern B) 専念 |
| Remote VPS Hermes (Pattern C) | ⏸ 範囲外 | 同上 |

## 3. 機能要件

### FR-1: 検索

- F1.1 設定ファイル `config/keywords.yaml` の `themes.<topic_id>.keywords` を CLI `--topic` に応じて発射
- F1.2 Provider Adapter (mock / hermes / xai / x_api) で切替可能
- F1.3 各 query は `time_range` (24h / 3d / 7d) と `topic_id` を伝搬
- F1.4 結果は `SearchResult` 型: `items` (StructuredPost or SearchCitationResult の Union)、`capabilities`、`missing_fields` を含む

### FR-2: 正規化・重複排除

- F2.1 URL + 本文ハッシュで重複排除
- F2.2 `VerificationTags` (status / source_type / risk_flags) を自動付与

### FR-3: スコアリング

- F3.1 5 軸 (importance / novelty / career_relevance / note_fit / x_fit) を 0-10 で算出
- F3.2 加重は `config/output.yaml::scoring.weights`、合計が 0.99-1.01 の範囲
- F3.3 engagement metrics が無い場合は `citation_fallback` (citation_count + provider confidence)
- F3.4 career_relevance は `config/profile.yaml::focus_atoms_high/medium/low` を atom 単位でマッチ + target_company ブースト

### FR-4: LLM Adapter

- F4.1 `LLMProvider` 抽象 (`mock` / `claude` / `grok-stub`) を CLI `--llm-provider` で選択
- F4.2 API key 未設定時は `mock` に fallback、`run_manifest.fallback_used` に明示記録
- F4.3 Claude adapter は `claude-opus-4-7` 等の新モデルで `temperature` が rejected された場合、自動再試行
- F4.4 channel ごとの `max_tokens` は `config/output.yaml::llm.max_tokens` で制御

### FR-5: トレンド要約

- F5.1 topic ごとに `TrendSummary` (main_points / sentiment / emerging_keywords / short_jp_explanation / content_angles)
- F5.2 LLM 呼び出しは `max_tokens.trend_summary` + `max_tokens.trend_angles` の 2 回

### FR-6: コンテンツドラフト

- F6.1 4 channel: `x_post` / `x_thread` / `note_outline` / `linkedin`
- F6.2 各 draft は **originality guard 6 fields**: `source_urls` / `source_summary` / `my_angle` / `draft_text` / `originality_note` / `needs_review` を必ず保持
- F6.3 LinkedIn は `length_mode` (short / standard / long) で語数レンジ制御
- F6.4 元投稿との一致率が 80% を超えた場合は 1 回 retry

### FR-7: 動画/画像プロンプト

- F7.1 4 use case: `note_header` / `x_short` / `linkedin_visual` / `youtube_shorts`
- F7.2 静止画 (note_header / linkedin_visual) と動画 (x_short / youtube_shorts) で異なるテンプレ
- F7.3 EN prompt (Grok Imagine 投入用) + 日本語説明 の bilingual

### FR-8: 出力成果物

- F8.1 `outputs/daily_reports/<date>/report.md` (Top10 + Trend Summary)
- F8.2 `outputs/daily_reports/<date>/run_manifest.json` (再現性 + 品質シグナル)
- F8.3 `outputs/csv/<date>.csv` (全 deduped items の scoring 詳細)
- F8.4 `outputs/excel/<date>_x_intelligence_report.xlsx` (5 sheets: Top10 / AllItems / TrendSummary / ContentIdeas / VideoPrompts)
- F8.5 `outputs/content_drafts/<date>/01_x_post.md` 他 3 件
- F8.6 `outputs/video_prompts/<date>/01_note_header.md` 他 3 件
- F8.7 `outputs/review_queue/<date>/drafts_to_review.md` + `approved/` + `rejected/` + `needs_fact_check/`
- F8.8 Hermes provider 使用時は `outputs/raw_responses/hermes/<date>/<id>.stdout|.stderr|.meta.json` (gitignore 対象)

### FR-9: HITL レビューキュー

- F9.1 全 draft は `needs_review: True` で生成
- F9.2 レビュー後は手動でファイル移動 (approved / rejected / needs_fact_check)
- F9.3 自動投稿は **絶対に行わない**

## 4. 非機能要件

### NFR-1: 再現性

- 同一 config + 同一 fixtures (mock の場合) で同一 `config_hash` + `fixture_hash` が manifest に記録される
- LLM 出力は非決定的だが、入力側は完全に再現可能

### NFR-2: 拡張性

- 新 Provider を追加するときは `SearchProvider` 抽象を継承、`Capabilities` を真実に基づき定義
- 新 LLM を追加するときは `LLMProvider` 抽象を継承

### NFR-3: 可観測性

- すべての run で `run_manifest.json` を生成
- `fallback_used` / `warnings` / `citationless_*` / `missing_fields_summary` を毎 run に記録
- silent fallback 禁止（必ず warning + manifest に記録）

### NFR-4: テスト

- 本書作成時点で **pytest 138 passed, 1 skipped**
- `tests/integration/test_hermes_live.py` は `HERMES_LIVE_TESTS=1` 環境変数で有効化
- 自動投稿禁止 negative test は parametrized で全 .py スキャン

## 5. 安全性・コンプライアンス要件

### SR-1: Human-in-the-loop 方針

- すべての content draft は `needs_review: True`
- レビュー後の手動ファイル移動でレビュー状態を管理
- 投稿アクションは人間が手動で行う

### SR-2: 自動投稿しない方針

- `tests/test_no_auto_posting_capability.py` で以下を常時検証:
  - posting 系関数名 (`post_to_x`, `tweet`, `publish_post` 等) が src/ + scripts/ に存在しない
  - 投稿 SDK (`tweepy`, `python-twitter`, `linkedin-api` 等) を import していない
  - write endpoint URL (`api.twitter.com/2/tweets/manage`, `linkedin.com/v2/posts` 等) を参照していない
  - `requirements.txt` に投稿 SDK を pin していない
  - `README.md` に "draft generation only" 系のマーカーが明記されている

### SR-3: API key 取扱い

- `ANTHROPIC_API_KEY` / `XAI_API_KEY` 等は `.env` (gitignore 対象) のみで管理、コード直書き禁止
- Hermes credentials は CLI 側 (`~/.hermes/.env`) で自管理、本プロジェクトは触らない
- `RunManifest` に secret 系フィールド名を持たない (`tests/test_no_secret_in_manifest.py` で検証)
- `src/utils/logger.py` は環境変数を列挙しない
- subprocess の stdout/stderr は `src/utils/redact.py::redact()` を必ず通してから永続化

### SR-4: 引用元保持

- 全 Top10 アイテムは `cited_urls` または `url` を必ず保持
- 全 content draft は `source_urls` を必ず保持
- `tests/test_source_url_preservation.py` で検証

### SR-5: Fact-check tagging

- `VerificationTags`: `verification_status` (unverified / single_source / multi_source_confirmed / official_source_confirmed / needs_manual_check)、`source_type` (official / founder_executive / engineer_dev / media / influencer / unknown)、`risk_flags` (rumor / hype / investment_claim / product_claim / pricing_claim / legal_or_policy_claim / security_claim)
- LLM 出力には保守的に `[要事実確認]` マーカーを付ける運用

### SR-6: Citation 品質シグナル

- `citationless_items_count` / `citationless_ratio` / `topics_with_high_citationless_ratio` を manifest と report.md に表示
- `🟢 < 20%` / `🟡 20-50%` / `🔴 ≥ 50%` の経験則

## 6. 利用する外部サービス

| サービス | 用途 | 本書作成時点の状態 |
|---|---|---|
| **X Premium+ / SuperGrok** | xAI OAuth ログイン経由で Hermes の `x_search` ツールを利用 | 柴田さん env で xAI OAuth ログイン済確認 |
| **xAI Grok 4.3** | Hermes 経由で実呼び出し (`hermes doctor` で provider: xai-oauth, model: grok-4.3) | x_search tool 利用可 |
| **Hermes Agent v0.14.0** (Nous Research) | WSL2 Ubuntu 上にインストール、`hermes -z "<query>" -t x_search` で呼び出し | Pattern B (WSL2) で動作確認済 |
| **Claude API** (Anthropic) | 要約・スコアリング補助・コンテンツドラフト生成 | `claude-opus-4-7` で動作確認済、`temperature` deprecated 対応済 |
| (将来) X API v2 | tweets/search/recent で StructuredPost 取得 | 未実装 (stub) |
| (将来) Grok Imagine API | 実画像/動画生成 | 未実装 (prompt 生成までで停止) |

## 7. 出力成果物 (まとめ)

```
outputs/
├── daily_reports/<date>/
│   ├── report.md             (Top10 + Trend Summary、citation 品質シグナル付き)
│   └── run_manifest.json     (再現性 + 品質シグナル)
├── csv/<date>.csv            (全 deduped items の scoring 詳細)
├── excel/<date>_x_intelligence_report.xlsx  (Top10 / AllItems / TrendSummary / ContentIdeas / VideoPrompts)
├── content_drafts/<date>/
│   ├── 01_x_post.md
│   ├── 02_x_thread.md
│   ├── 03_note_outline.md
│   └── 04_linkedin.md
├── video_prompts/<date>/
│   ├── 01_note_header.md
│   ├── 02_x_short.md
│   ├── 03_linkedin_visual.md
│   └── 04_youtube_shorts.md
├── review_queue/<date>/
│   ├── drafts_to_review.md
│   ├── approved/
│   ├── rejected/
│   └── needs_fact_check/
└── raw_responses/hermes/<date>/   (gitignore 対象、Hermes provider 使用時のみ)
    ├── <ts>_<topic>_<hash>.stdout
    ├── <ts>_<topic>_<hash>.stderr
    └── <ts>_<topic>_<hash>.meta.json
```

すべての出力ディレクトリは `.gitignore` で除外（`outputs/examples/` のみコミット可）。
