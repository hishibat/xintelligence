# X Intelligence & Content Automation Skills (MVP)

X 上の重要情報を効率的に収集 → 重要度判定 → Markdown / CSV / Excel / 投稿案 / 動画プロンプトまで一気通貫で出すローカルスキル群。**Human-in-the-loop 前提・自動投稿は実装しない**。

> ⚠️ **MVP は draft generation only / 投稿実行機能なし。**
> 本リポジトリは X 投稿・LinkedIn 投稿・Note 公開を **行いません**。draft text の生成までで停止し、`outputs/review_queue/` への手動移動でレビュー状態を管理します。投稿アクションは人間が手動で実行してください。
> この方針は `tests/test_no_auto_posting_capability.py` で **negative test** として常時検証されます（posting 系の関数名・write endpoint URL・posting SDK の混入を CI で防止）。

## 標準運用方針（2026-05-21 — Hermes IV 検証後に確定）

| 用途 | 推奨コマンド |
|---|---|
| **検証 (validation)** | `--search-fallback none` で fail-loud。新 provider / 新 prompt を実機検証するとき |
| **日次運用 (daily)** | `--search-fallback mock` で resilient。一部 query が失敗しても他で artifact が出る |
| **実行単位** | **topic 分割**。1 コマンド = 1 topic (3-5 query × 30-60s ≈ 2-5 分) |
| **`--topic all` 一括** | **原則非推奨**。週次集約 / 手動バッチ用途のみ。実時間 20-60 分、途中失敗時の影響範囲が大きい |

### 日次運用の典型コマンド (topic 分割 / 並列)

```powershell
# PowerShell から topic 別に並列起動
foreach ($t in @("ai_agent","claude_code","hermes_openclaw","grok_xai",
                 "competing_llms","ai_infra_vendors","ai_governance_data",
                 "career_consulting")) {
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "cd 'C:\Users\Hideyuki Shibata\workspace\company\Content_Production\x-intelligence'; " +
        "python scripts\run_daily.py --provider hermes --llm-provider claude " +
        "--search-fallback mock --topic $t --date $(Get-Date -Format 'yyyy-MM-dd')"
    )
}
```

### Citation 品質シグナル

各 run の `report.md` および `run_manifest.json` に以下を出力。**毎朝レビュー時の最初のチェック項目**として使用:

- `citationless_items_count` — citation_urls が空の SearchCitationResult 件数
- `citationless_ratio` — 全 deduped items に対する比率 (0.0-1.0)
- `topics_with_high_citationless_ratio` — 50% 超の topic 一覧 (要再実行 / prompt 調整シグナル)

経験則:
- 🟢 `< 20%` → 健全
- 🟡 `20-50%` → 要観察
- 🔴 `≥ 50%` → 該当 topic だけ prompt 強化または再実行

## 現時点の安定版 MVP でできること（2026-05-21）

| 項目 | 状態 |
|---|---|
| mock data + Claude LLM で E2E 運用 | ✅ 動作確認済 (`--provider mock --llm-provider claude`) |
| 本物の X 検索 (X API v2) | ❌ 未実装。`search_x_api.py` は stub |
| Hermes Agent 経由の X 検索 | ❌ 未実装。`search_hermes.py` は stub。次フェーズ |
| xAI Responses + x_search 経由 | ❌ 未実装。`search_xai.py` は stub。次フェーズ |
| LLM 切替 (Claude / mock / Grok) | 🟡 Claude / mock 実装済、Grok stub |
| 自動投稿 | ❌ 未実装 (恒久的に実装しない方針)。`tests/test_no_auto_posting_capability.py` で常時検証 |
| Human review gate (`needs_review`) | ✅ 必須。全 draft に `True` 付与 |
| Fact-check tagging (`verification_status` / `risk_flags`) | ✅ 自動付与 |
| LLM トークン予算の channel 別 config | ✅ `config/output.yaml::llm.max_tokens` で制御 |
| LinkedIn 投稿の length モード (short/standard/long) | ✅ `config/output.yaml::content.linkedin.length_mode` |
| Video prompt の用途別品質 (静止画/動画) | ✅ note_header=静止画、x_short/youtube_shorts=動画、linkedin_visual=静止画 |
| reproducibility (`config_hash` + `fixture_hash`) | ✅ `run_manifest.json` で記録 |
| silent fallback 防止 | ✅ `fallback_used` + `warnings` で明示、`check_claude_llm.py` は fallback 禁止 |

## LLM トークン予算 (デフォルト値)

`config/output.yaml::llm.max_tokens` で制御。MVP の既定値:

| 用途 | デフォルト max_tokens | 用途 | デフォルト max_tokens |
|---|---|---|---|
| `why_important` | 200 | `x_thread` | 1000 |
| `trend_summary` | 800 | `note_outline` | 1600 |
| `trend_angles` | 400 | `linkedin` | 1200 |
| `x_post` | 500 | `video_concept` | 200 |
| | | `video_scene` | 400 |

note_outline が途中切れする場合は `note_outline: 2000` 等に増やす。

## このリポジトリの目的

- 毎朝 1 コマンドで「今日見るべき AI / テック関連 X 投稿 Top 10 + トレンド要約 + X / Note / LinkedIn 投稿案 + Grok Imagine 用画像/動画プロンプト」を取り出す
- Provider Adapter で `mock` / `hermes` / `xai` / `x_api` を差し替え可能にし、MVP は mock で完全 E2E
- 引用元 URL は必ず保持、誤情報 / 価格 / 仕様 / 法務系は `risk_flags` で明示

## 全体アーキテクチャ

```
config/ → Search Provider Adapter → Dedupe → Verification Tagging →
   Scoring (profile.yaml 参照) → LLM Adapter → Trend / Content / Video →
   outputs/{daily_reports, csv, excel, content_drafts, video_prompts, review_queue}
   + outputs/daily_reports/YYYY-MM-DD/run_manifest.json
```

詳細は [docs/design-lite.md](docs/design-lite.md)。

## 利用する外部サービス（差し替え可能）

| 機能 | 想定実装 | MVP 状態 |
|---|---|---|
| X 検索 | mock (fixtures) / Hermes x_search / xAI Responses+x_search / X API v2 | **mock のみ実装**、他は stub |
| LLM | mock / Claude (Anthropic SDK) / Grok | mock + Claude（key 未設定で auto fallback） |
| 画像/動画生成 | Grok Imagine API（公式提供）— **MVP は prompt 生成のみ** | prompt only |

### 推奨現行モデル名（2026-05 時点）

- Claude: `claude-opus-4-7` (本MVPの既定。テキスト要約・スコアリング用)
- Grok: `grok-4` (Responses API + x_search tool)
- Grok 画像: `grok-2-image`（旧モデル）— 推奨は **Grok Imagine の最新 image エンドポイント**（要 xAI ドキュメント確認）
- Grok 動画: `grok-imagine`（image/video 共通の最新提供枠）

> 注: モデル名は xAI 側で頻繁に切替わるため、本番投入前に `https://docs.x.ai/` で要再確認。

## Pattern 別セットアップ

### Pattern A: Pure Python MVP only（Windows PowerShell）

mock mode で完結する最小構成。Hermes / xAI なしで動作。

```powershell
cd C:\Users\Hideyuki Shibata\workspace\company\Content_Production\x-intelligence
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# 編集不要 (mock 既定で動く)
pytest -q
python scripts\run_daily.py --provider mock
```

### Pattern B: Hermes integration（WSL2 必須）

Hermes Agent を WSL2 Ubuntu で動かし、Python 側から `wsl bash -lc "hermes -z ..."` で呼ぶ構成。Step 0 probe (2026-05-21) で確定した手順。

#### 1) WSL2 で Hermes をインストール

```powershell
# Windows PowerShell から
wsl bash -c "curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash"
wsl bash -lc "hermes doctor"   # ✓ が並ぶ
```

#### 2) xAI OAuth ログイン（ブラウザ認証）

```powershell
wsl hermes model
# 対話プロンプトで xAI provider を選択 → ブラウザで X Premium+ / SuperGrok 認証
```

完了確認:
```powershell
wsl hermes doctor | findstr "xAI OAuth"
# 期待出力: ✓ xAI OAuth (logged in)
```

#### 3) `x_search` ツール有効化（多くの環境ではデフォルト ON）

```powershell
wsl hermes doctor | findstr "x_search"
# 期待: ✓ x_search
# 出ない場合: wsl hermes tools enable x_search
```

#### 4) 接続診断 (fallback 禁止)

```powershell
cd "C:\Users\Hideyuki Shibata\workspace\company\Content_Production\x-intelligence"
python scripts\check_hermes.py
# 全 6 項目 [OK] で終了コード 0
```

#### 5) Hermes 経由で run_daily を実行

**初回検証 (fail-loud)**:
```powershell
python scripts\run_daily.py --provider hermes --llm-provider claude --search-fallback none
```

**日次運用 (resilient)**:
```powershell
python scripts\run_daily.py --provider hermes --llm-provider claude --search-fallback mock
```

#### 接続失敗時の挙動

| Hermes 状態 | `--search-fallback none` | `--search-fallback mock` |
|---|---|---|
| 成功 | exit 0, `fallback_used=[]` | exit 0, `fallback_used=[]` |
| 失敗 | **exit ≠ 0、partial write なし** | exit 0, `fallback_used=["search:hermes->mock"]`, warning 記録 |

#### Hermes が返すデータの粒度

Hermes の `x_search` (Grok 4.x 経由) は **検索結果の合成テキスト + Source URLs** を返す。投稿本文 / author / created_at / engagement metrics は取得できないため、本リポジトリは `SearchCitationResult` 型で表現し、`missing_fields` に欠損項目を明示。`scoring.py` は `citation_fallback` 経路で自動対応。

### Pattern C: Remote / VPS Hermes（将来拡張）

VPS / リモートホスト上で Hermes を常駐させ、ローカルからは API 越しに叩く構成。

- OAuth over SSH は xAI 側のリダイレクト URI 制約に注意（localhost 限定の場合は port forward が必要）
- `HERMES_OAUTH_TOKEN` をローテーションする際に同期手順を明文化すること
- アカウント制限・rate limit がリモート IP 単位でかかる可能性あり

## MVP 実行方法

```powershell
# 1) install
pip install -r requirements.txt

# 2) test
pytest -q

# 3) one-shot daily run (mock)
python scripts\run_daily.py --provider mock

# 4) inspect outputs
explorer outputs\daily_reports
```

### CLI オプション

```
--provider {mock,hermes,xai,x_api}   (default: mock)
--llm-provider {mock,claude,grok}    (default: env LLM_PROVIDER or mock)
--date YYYY-MM-DD                    (default: today UTC)
--time-range {24h,3d,7d}             (default: 24h)
--topic <theme_id|all>               (default: all)
--output-dir <path>                  (default: ./outputs)
--dry-run                            run pipeline, skip file writes
--no-llm                             force LLM provider to mock
```

## 認証情報の設定方法

- **API key を絶対にコードに直書きしない**（`ANTHROPIC_API_KEY` / `XAI_API_KEY` / `HERMES_OAUTH_TOKEN` 等すべて）
- `.env` は **絶対に commit しない**（`.gitignore:2` で除外、`git check-ignore -v .env` で検証可）
- `.env.example` をコピーして必要な key だけ埋める
- `RunManifest` に key / token / secret 系のフィールドは **持たない**（`tests/test_no_secret_in_manifest.py` で検証）
- `logger` は環境変数を列挙しない（`src/utils/logger.py` 参照）
- Claude API key が未設定なら自動で `mock` に fallback し、`outputs/.../run_manifest.json` の `fallback_used` に記録される（silent fallback はしない）
- ただし `scripts/check_claude_llm.py` は **fallback 禁止**（接続テスト目的のため、key 無しなら明示的に失敗）

## 出力例

```
outputs/
├── daily_reports/2026-05-20/
│   ├── report.md
│   └── run_manifest.json
├── csv/2026-05-20.csv
├── excel/2026-05-20_x_intelligence_report.xlsx   (Top10/AllItems/TrendSummary/ContentIdeas/VideoPrompts)
├── content_drafts/2026-05-20/
│   ├── 01_x_post.md
│   ├── 02_x_thread.md
│   ├── 03_note_outline.md
│   └── 04_linkedin.md
├── video_prompts/2026-05-20/
│   ├── 01_note_header.md
│   ├── 02_x_short.md
│   ├── 03_linkedin_visual.md
│   └── 04_youtube_shorts.md
└── review_queue/2026-05-20/
    ├── drafts_to_review.md
    ├── approved/
    ├── rejected/
    └── needs_fact_check/
```

## Fact-check / 安全性

- **重要ニュースや価格・仕様・法務・API 制限に関する情報は、X だけで判断せず、公式ドキュメントまたは複数ソース確認を必須にする**
- 各投稿に `verification_status` (unverified / single_source / multi_source_confirmed / official_source_confirmed / needs_manual_check)、`source_type`、`risk_flags` を付与
- LLM 出力は保守的に `[要事実確認]` マーカーを付ける

## Human-in-the-loop

- すべての content_drafts は `needs_review: true` で作成される
- レビュー後は手動で `outputs/review_queue/YYYY-MM-DD/{approved,rejected,needs_fact_check}/` に移動
- 自動投稿は **MVP では実装しない**（将来 Phase 7 以降）

## 今後の拡張案

| Phase | 内容 | トリガー |
|---|---|---|
| 2 | Hermes adapter 実装 | WSL2 上で Hermes 起動 + OAuth 検証完了 |
| 3 | xAI Responses + x_search 直接連携 | `XAI_API_KEY` 入手 + quota 把握 |
| 4 | xlsx ピボット拡張 | MVP 1 ヶ月運用後 |
| 5 | scheduled-tasks 経由の日次自動実行 | AI_Usage_Review v0.2 凍結解除後 |
| 6 | **Grok Imagine API direct integration**（公式に提供済の image/video API を呼ぶ） | `XAI_API_KEY` または Hermes OAuth で生成成功を検証済 / quota・費用・著作権ポリシー確認済 |
| 7 | Streamlit レビュー UI | 手動運用 1 ヶ月で課題抽出後 |
| 8 | OpenClaw 統合（投稿実行レイヤー） | OpenClaw 安定版リリース後 |

## 実 outputs と git

実行ごとの `outputs/daily_reports/`, `outputs/csv/`, `outputs/excel/`, `outputs/content_drafts/`, `outputs/video_prompts/`, `outputs/review_queue/` は **原則 git 管理しない**（実データ・個人視点コメント・誤情報リスクが混在するため）。共有用サンプルは `outputs/examples/` に置けばコミット可。
