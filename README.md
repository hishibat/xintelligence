# X Intelligence & Content Automation Skills (MVP)

X 上の重要情報を効率的に収集 → 重要度判定 → Markdown / CSV / Excel / 投稿案 / 動画プロンプトまで一気通貫で出すローカルスキル群。**Human-in-the-loop 前提・自動投稿は実装しない**。

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

### Pattern B: Hermes integration（WSL2 推奨）

Hermes Agent はもともと Linux/macOS を主ターゲットにしている。Windows ユーザは WSL2 上で Hermes を動かし、Windows 側 workspace と path 共有する。

```bash
# WSL2 (Ubuntu) 上で
sudo apt update && sudo apt install -y python3.11 python3.11-venv
git clone https://github.com/NousResearch/hermes  # 実 URL は公式リリース参照
cd hermes && ./install.sh
hermes auth login  # X Premium+ / SuperGrok の OAuth フロー
hermes tools enable x_search
hermes tools status

# Windows 側 workspace は /mnt/c/Users/.../workspace で見える
cd /mnt/c/Users/Hideyuki\ Shibata/workspace/company/Content_Production/x-intelligence
X_SEARCH_PROVIDER=hermes HERMES_ENABLED=true python scripts/run_daily.py --provider hermes
```

Hermes 接続検証チェックリスト:

- [ ] `hermes auth status` で OK
- [ ] `hermes tools status` で `x_search` が enabled
- [ ] xAI OAuth token が有効（Premium+ または SuperGrok 契約状態）
- [ ] `XAI_API_KEY` fallback が機能（OAuth 切れ時）
- [ ] OAuth 優先・API key fallback の順序が `.env` に反映済

> Hermes が x_search で返す結果は **Grok によるサーバーサイド検索結果の合成 + citations** が中心。投稿本文や engagement metrics は完全には取れない可能性が高い。本リポジトリは `SearchCitationResult` で表現し、欠損は `missing_fields` に明示する。

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

- `.env` は **絶対に commit しない**（`.gitignore` で除外済）
- `.env.example` をコピーして必要な key だけ埋める
- Claude API key が未設定なら自動で `mock` に fallback し、`outputs/.../run_manifest.json` の `fallback_used` に記録される（silent fallback はしない）

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
