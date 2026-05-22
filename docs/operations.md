# operations.md — X Intelligence & Content Automation Skills

> 本書は output quality polish (commit `5d9898c`) 完了後の **運用手順書 Runbook** (2026-05-22 時点)。
> セットアップ手順は `README.md`、要件は `docs/requirements.md`、内部設計は `docs/design.md` を参照。
> Hermes CLI 実態仕様は `docs/hermes_cli_spec.md` 参照。

## 0. Streamlit UI (review console)

CLI 出力ファイルをブラウザで確認・分類するためのローカル UI。**投稿機能なし**、
ファイル移動とローカル subprocess 起動のみ。

### 0.1 起動

```powershell
cd "C:\Users\Hideyuki Shibata\workspace\company\Content_Production\x-intelligence"
python -m streamlit run ui/streamlit_app.py
```

ブラウザで `http://localhost:8501` が自動で開く。

> なぜ `python -m streamlit run` か:
> Windows ユーザーサイト install (`pip install --user` / 書込権限制限環境)
> では `streamlit.exe` が `%APPDATA%\Python\Python3xx\Scripts\` に入り
> PATH に通っていないケースがある。`python -m streamlit run` は
> どの環境でも動くため正規ルートに採用。

### 0.2 UI でできること

| 機能 | 詳細 |
|---|---|
| Pipeline 起動 | Sidebar の Run button で `scripts/run_daily.py` を subprocess 実行。引数 (topic / provider / llm_provider / search_fallback / date) は UI で選択。stdout/stderr は折りたたみ表示 |
| Daily Report tab | `report.md` を Markdown 表示。`run_manifest.json` の主要項目を 🟢🟡🔴 カードで可視化 (citationless_ratio / fallback_used / warnings / topics_with_high_citationless_ratio) |
| Drafts tab | `01_x_post.md` / `02_x_thread.md` / `03_note_outline.md` / `04_linkedin.md` をサブタブで切替表示 |
| Video Prompts tab | `01_note_header.md` / `02_x_short.md` / `03_linkedin_visual.md` / `04_youtube_shorts.md` を表示 |
| Review Queue tab | 各 draft に `approved / rejected / needs_fact_check` 移動ボタン (純粋なローカル `shutil.move` のみ、外部送信なし) + bucket 内のファイル一覧 |
| Files tab | 当該 run の全 outputs ファイルパスを表示 |

### 0.3 UI でできないこと (恒久禁止)

- **X / Note / LinkedIn への投稿** — Streamlit UI は **絶対に投稿しない**。
- **外部 API への送信** — Move ボタンは `shutil.move` のみ、ネットワーク呼び出しなし。
- **`.env` の書き換え** — UI は環境変数を読み取らず、key 操作もしない。
- **outputs 外のファイル操作** — File Path 検証で project root 外の操作はエラー。

これらは `tests/test_no_auto_posting_capability.py` が `ui/` 配下も含めて
常時検証 (本 commit から ui/ が scan 対象に追加)。万一 posting endpoint /
SDK / 関数名が混入すると pytest が即時 fail。

### 0.4 UI 推奨ワークフロー (毎朝)

```
1. python -m streamlit run ui/streamlit_app.py
2. Sidebar で topic 選択 (e.g. claude_code) → Run
   → 完了通知を待つ (1-5 分)
3. Daily Report tab で manifest カードを確認
   - 🟢 なら次へ / 🔴 なら該当 topic 再実行
4. Drafts tab で 4 channel を順に読む
5. Review Queue tab で各 draft を approved / rejected / needs_fact_check に分類
6. approved/ にあるファイルを開き、手動で X / Note / LinkedIn に投稿
```

UI を使わない場合の手順は §2 以降の CLI 手順を参照。

---

## 1. 前提

### 1.1 必要な環境

- Windows + WSL2 Ubuntu (Pattern B)
- Hermes Agent CLI が WSL2 にインストール済、`hermes doctor` で:
  - `✓ xAI OAuth (logged in)`
  - `✓ x_search` (Tool Availability セクション)
- `.env` に `ANTHROPIC_API_KEY` 設定済（gitignore 対象、git に絶対 commit しない）
- Python 3.11+、pip install 済み

セットアップ手順詳細は `README.md` の Pattern B セクション参照。

### 1.2 接続診断 (異常時の最初の一手)

```powershell
python scripts\check_claude_llm.py     # Claude API 疎通
python scripts\check_hermes.py         # Hermes 6 項目 (fallback 禁止)
```

両方 `[OK]` で exit 0 なら本番運用可。1 つでも FAIL なら下記トラブルシュート §7 参照。

## 2. 日次運用手順

### 2.1 推奨実行方式 — topic 単位実行

**`--topic all` は原則非推奨**（38 query 一括で 20-60 分かかり、1 query 失敗で全体ブロック / 全体遅延）。
推奨は **topic 単位 (3-5 query / topic、各 2-5 分)** に分割。

### 2.2 mode の使い分け

| 用途 | フラグ | 期待挙動 |
|---|---|---|
| **検証 (validation)** | `--search-fallback none` | Hermes 失敗時 exit ≠ 0 で即停止。 新 prompt / 新 provider 投入時に問題を即発見 |
| **日次運用 (daily)** | `--search-fallback mock` | Hermes 失敗時 mock に降格、`fallback_used` + `warnings` に記録、全 artifact は出る |

### 2.2.1 Streamlit UI でハンズオン確認するとき

Streamlit Review Console (`python -m streamlit run ui/streamlit_app.py`) で
触る時の推奨は **`time_range=24h` + `search_fallback=mock`**。

| ケース | 推奨設定 | 理由 |
|---|---|---|
| **ハンズオン / デモ** | `time_range=24h`, `search_fallback=mock` | Hermes は通常 30-60s で返る。万一失敗しても mock 降格で artifact は出る |
| **新 prompt / 新 topic の検証** | `time_range=24h`, `search_fallback=none` | fail-loud で問題を見逃さない |
| **週末 catch-up (3d/7d)** | `time_range=3d` or `7d`, `search_fallback=mock` | x_search が広 query で 180s を超えやすい。mock 降格で完走優先 |
| **3d/7d を fail-loud で通したい** | `search_fallback=none` + `HERMES_TIMEOUT_SECONDS=300` を `.env` に追加 | default 180s では足りないケース。`.env` 変更後は Streamlit 再起動が必要 |

> 🚨 **やってはいけない組み合わせ**: `provider=hermes` + `search_fallback=none` + `time_range=7d` + broad topic (enterprise_ai_adoption / frontier_models / ai_agents / multi_agent_systems) — 180s timeout で確実に `exit 4` する。UI には pre-run warning が出るので、それに従って `search_fallback=mock` に切り替えるか、上記の timeout 延長を行うこと。

### 2.2.2 `HERMES_TIMEOUT_SECONDS` の default を変えない理由

UI に warning を追加した時点 (2026-05-22) では、default 180s を維持する。

- 24h run は 30-60s で returns する想定 → 180s で十分
- 300s に default を引き上げると 24h run の異常 (Hermes hang) を 2 分余分に待つことになる
- まず UI warning で「ユーザーが事前に回避できる UX」を観測する
- それでも timeout 多発するようなら default 引き上げを再検討（一律ではなく、`time_range=7d` 選択時のみ動的に extend する案も含めて）

### 2.3 朝の標準オペレーション (例)

```powershell
cd "C:\Users\Hideyuki Shibata\workspace\company\Content_Production\x-intelligence"
$today = Get-Date -Format "yyyy-MM-dd"

# topic を 8 つ並列起動 (各 2-5 分、wall clock 5-10 分で完了見込み)
foreach ($t in @("claude_code", "ai_agents", "frontier_models", "multi_agent_systems",
                 "ai_infrastructure", "data_platforms", "ai_governance",
                 "enterprise_ai_adoption")) {
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "cd 'C:\Users\Hideyuki Shibata\workspace\company\Content_Production\x-intelligence'; " +
        "python scripts\run_daily.py --provider hermes --llm-provider claude " +
        "--search-fallback mock --topic $t --date $today"
    )
}

# 完了後、出力ディレクトリを開いてレビュー
explorer outputs\daily_reports\$today
explorer outputs\content_drafts\$today
explorer outputs\review_queue\$today
```

> 後続セッションで `scripts/run_daily_per_topic.py` (1 コマンドで topic 並列起動 + 集約) を実装予定。本書作成時点では上記 PowerShell loop で運用。

## 3. 実行例 (代表 4 topic)

### claude_code (5 queries, ~3-5 分)

```powershell
python scripts\run_daily.py --provider hermes --llm-provider claude `
    --search-fallback none --topic claude_code --date 2026-05-21
```
- 本書作成時点での citation 品質: 安定して 🟢 (citationless 0%)

### multi_agent_systems (6 queries, ~3-4 分)

```powershell
python scripts\run_daily.py --provider hermes --llm-provider claude `
    --search-fallback none --topic multi_agent_systems --date 2026-05-21
```
- 旧 `hermes_openclaw` の後継。Hermes / CrewAI / LangGraph / multi-provider を包含。citation 品質は旧 hermes_openclaw 同等 (0-10%) を想定（要再計測）

### ai_agents (5 queries, ~3-5 分)

```powershell
python scripts\run_daily.py --provider hermes --llm-provider claude `
    --search-fallback none --topic ai_agents --date 2026-05-21
```
- 安定して 🟡 (citationless ~20%、Grok が広い query で稀に x_search 呼ばないケースあり)

### frontier_models (6 queries, ~3-5 分)

```powershell
python scripts\run_daily.py --provider hermes --llm-provider claude `
    --search-fallback none --topic frontier_models --date 2026-05-21
```
- 旧 `grok_xai` + `competing_llms` を統合。Grok 自己言及対策の TOPIC_PROMPT_OVERRIDES は `frontier_models` key に rebrand 済
- 旧 grok_xai 単独計測 (commit `c302060`) では 3-run 平均 35%。frontier_models 統合後は GPT/Gemini/Claude 由来の query が混ざるため再計測必要

## 4. 出力確認手順

### 4.1 まず `run_manifest.json` を見る

```powershell
type outputs\daily_reports\$today\run_manifest.json
```

確認順:

1. `provider` と `llm_provider` が想定通りか
2. `fallback_used` が空か（空なら 🟢 真の経路で完走）
3. `warnings` が空か
4. `citationless_items_count` / `citationless_ratio` / `topics_with_high_citationless_ratio`
5. `missing_fields_summary` で provider 別の欠損が想定通りか

### 4.2 `report.md` の冒頭で品質シグナルを確認

```
# X Intelligence Daily Report — 2026-05-21
- run_id: `20260521T...`
- provider: `hermes`
- llm_provider: `claude`
- fallback_used: _(none — real LLM was reached)_
- 🟢 citationless_items: 0 (0.0%)
```

🟢 なら次へ。🟡/🔴 なら §5 へ。

### 4.3 Top10 を流し読み

各アイテムの:
- `verification_status` (`official_source_confirmed` が理想)
- `risk_flags` (`pricing_claim` / `legal_or_policy_claim` などが付いていれば要追加確認)
- `なぜ重要` Claude commentary が柴田さん視点で意味あるか

### 4.4 content_drafts/ を開く

- `01_x_post.md` — 180 字以内、自分の解釈ありか
- `02_x_thread.md` — 4-6 ポスト、論理展開と最後のキャリア示唆あるか
- `03_note_outline.md` — タイトル候補 3 + 見出し 6 + リード 80 字
- `04_linkedin.md` — `length_mode` (standard なら 600-900 words)、ビジネストーン

⚠️ **`originality_note` に `[WARNING] draft may be truncated`** が含まれる場合、
末尾が sentence terminator (`. 。 ! ? ！ ？` 等) で終わっていない可能性あり。
該当 channel の `config/output.yaml::llm.max_tokens.<channel>` を増やすか、
draft を読んで補完が必要か確認する (commit `5d9898c` 以降の機能)。

### 4.5 video_prompts/ を開く

- `01_note_header.md` — 静止画 16:9
- `02_x_short.md` — 動画 9:16 / 6-10s
- `03_linkedin_visual.md` — 静止画 1.91:1
- `04_youtube_shorts.md` — 動画 9:16 / 15-30s

`grok_imagine_prompt_en` をコピーして Grok Imagine に投入。

### 4.6 review_queue/ で投稿前管理

```
outputs/review_queue/<date>/
├── drafts_to_review.md     ← まずこれを開く
├── approved/               ← 投稿 OK のものを手動移動
├── rejected/               ← ボツのものを手動移動
└── needs_fact_check/       ← 公式情報で要確認のものを手動移動
```

レビュー後、`approved/` の draft を **人間が手動で** X / Note / LinkedIn に投稿。自動投稿は実装されていない。

## 5. Citation 品質の見方

### 5.1 🟢 / 🟡 / 🔴 の意味と対応

| 状態 | 範囲 | 対応 |
|---|---|---|
| 🟢 | citationless_ratio < 20% | 健全。そのまま次工程へ |
| 🟡 | 20% ≤ ratio < 50% | 要観察。各 item の `cited_urls` を個別確認 |
| 🔴 | ratio ≥ 50% | 該当 topic を再実行、または `TOPIC_PROMPT_OVERRIDES` 追加を検討 |

### 5.2 🔴 のときの対応フロー

1. `report.md` の `topics_with_high_citationless_ratio` を確認
2. 該当 topic だけ単体で **3 回連続再実行** して mean を見る:
   ```powershell
   1..3 | % { python scripts\run_daily.py --provider hermes --llm-provider claude `
       --search-fallback none --topic <topic_id> --date $today }
   ```
3. 3-run mean でも ≥ 50% なら:
   - `TOPIC_PROMPT_OVERRIDES` に新 entry を追加する `docs/design.md::7.2` の採用基準を満たすか
   - 満たすなら追加実装を検討（grok_xai と同じパターン）

### 5.3 `fallback_used` があるときの対応

| 値 | 意味 | 対応 |
|---|---|---|
| `"llm:claude->mock"` | Claude が呼べなかった | `.env` の `ANTHROPIC_API_KEY` 確認、quota 確認、`check_claude_llm.py` で診断 |
| `"search:hermes->mock"` | Hermes が呼べなかった | `check_hermes.py` で診断、`hermes doctor` で xAI OAuth / x_search 状態確認 |

`fallback_used` が空でない run は **draft の質が大きく下がっている** ので、投稿前に手動で内容を厳しめにレビューする。

### 5.4 `warnings` があるときの対応

`warnings` の中身を確認:
- `"Hermes failed: timeout (180s)"` → 該当 topic だけ再実行 (timeout 180s で網羅できない query が稀に存在)
- `"Claude API key missing or SDK unavailable → ..."` → 上記 §5.3 と同じ
- `"non-empty stderr: ..."` → Hermes が標準エラーに何か出した。`outputs/raw_responses/hermes/<date>/<id>.stderr` を確認

## 6. source URL 確認ルール

### 6.1 投稿前に必ず行う 3 確認

1. **draft の `source_urls` の URL を 1 つ以上踏む** — 実在する X 投稿か確認
2. 投稿者が `verification_status: official_source_confirmed` か `founder_executive` か `engineer_dev` であることを確認（`unknown` / `influencer` は要追加確認）
3. `risk_flags` に `pricing_claim` / `legal_or_policy_claim` / `security_claim` が付いていれば **公式ドキュメントで裏取り**

> 補足 (commit `5d9898c` 以降): `config/official_handles.yaml` に登録済の handle
> (NousResearch / xai / AnthropicAI / awscloud 等) は自動で `source_type` が
> 階層分類され、`verification_status` も `official_source_confirmed` 等に
> 格上げされる。新たに「これは公式」と判明した handle は同 yaml に追記すれば
> 次回以降の run で自動反映される。

### 6.2 短縮 URL の扱い

- 本書作成時点では adapter は短縮 URL (`t.co/...`) を **生のまま** cited_urls に入れる場合がある
- 短縮 URL が含まれている draft は、手動展開してから判断
- 将来 redaction 拡張 (URL 短縮の展開・mask) は別フェーズ

## 7. 投稿前レビュー手順

```
1. outputs/review_queue/<date>/drafts_to_review.md を開く
2. 各 draft (01_x_post.md, 02_x_thread.md, 03_note_outline.md, 04_linkedin.md) を順に開く
3. 各 draft で:
   a. source_urls をクリックして実在確認 (§6.1)
   b. my_angle に柴田さん視点が入っているか
   c. draft_text が元投稿の丸写しでないか (originality_note 確認)
   d. needs_review: **True** であることを確認
4. 判定:
   - 投稿 OK         → outputs/review_queue/<date>/approved/<filename>.md に移動
   - ボツ            → outputs/review_queue/<date>/rejected/<filename>.md に移動
   - 公式裏取り必要  → outputs/review_queue/<date>/needs_fact_check/<filename>.md に移動
5. approved/ の draft を 手動で X / Note / LinkedIn に投稿
```

## 8. トラブルシュート

### 8.1 Hermes が動かない

| 症状 | 原因候補 | 対応 |
|---|---|---|
| `check_hermes.py` で `HERMES_VERSION FAIL` | WSL2 で `hermes` が PATH にない | WSL2 で `source ~/.bashrc`、または再 install (`README.md` Pattern B) |
| `HERMES_DOCTOR FAIL` | Hermes 自体が壊れた | WSL2 で `hermes doctor` を直接実行、`hermes doctor --fix` |
| `XAI_OAUTH FAIL` | OAuth 切れ | 下記 §8.2 |
| `X_SEARCH_TOOL FAIL` | tool 無効化 | WSL2 で `hermes tools enable x_search` |
| `SMOKE FAIL` (timeout) | xAI rate limit / 重い query | 1 分後 retry。それでも駄目なら xAI コンソールで quota 確認 |
| `SMOKE_HAS_URL FAIL` | Grok が x_search 呼ばずに直接答えた | check_hermes は 1 retry 入りなので再実行でほぼ復旧、複数回失敗なら別 query で smoke test |

### 8.2 xAI OAuth が切れた

```powershell
# WSL2 で
wsl bash -lc "hermes login"
# プロンプトに従い xAI provider を選び、ブラウザで X Premium+ / SuperGrok 認証

# 確認
wsl hermes doctor | findstr "xAI OAuth"
# 期待: ✓ xAI OAuth (logged in)
```

### 8.3 citations=0 が多い (citationless_ratio ≥ 50%)

§5.2 のフロー参照。

### 8.4 Claude が fallback した

| 症状 | 対応 |
|---|---|
| `manifest.fallback_used` に `"llm:claude->mock"` | `.env` の `ANTHROPIC_API_KEY` が空 / 不正 / quota 切れ |
| `check_claude_llm.py` で `[FAIL] ANTHROPIC_API_KEY is not set` | `.env` ファイルを開いて key を埋める。**コードに直書きしない** |
| `check_claude_llm.py` で `BadRequestError: temperature ...` | adapter 側で自動 retry 済 (commit `ed06fd3`)、もし出るなら adapter コード更新を確認 |
| `[FAIL] ... 429` 系 | quota 超過。Anthropic Console で確認 |

### 8.5 Excel 出力で `ModuleNotFoundError: No module named 'openpyxl'`

セットアップ抜け。commit `5d9898c` 以降は `RuntimeError` で明示誘導が出る:

```
RuntimeError: openpyxl is not installed. Excel output requires openpyxl>=3.1.
  Fix: pip install -r requirements.txt   (run from project root)
  Or:  pip install 'openpyxl>=3.1'
```

指示通り `pip install -r requirements.txt` を実行すれば解決。`pyproject.toml`
と `requirements.txt` の双方に `openpyxl>=3.1` が pin されているため、再現性
は確保されている。

### 8.6 raw_response に不安がある (secret 漏洩懸念)

```powershell
# 全 raw response を redact で再 scan
cd "C:\Users\Hideyuki Shibata\workspace\company\Content_Production\x-intelligence"
python -c "
import re
from pathlib import Path
risky = [re.compile(r'\bsk-[A-Za-z0-9\-_]{20,}'),
         re.compile(r'\bxai-[A-Za-z0-9\-_]{20,}'),
         re.compile(r'eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}'),
         re.compile(r'(?i)\bbearer\s+[A-Za-z0-9\-_\.~+/=]{20,}')]
total, leaks = 0, 0
for f in Path('outputs/raw_responses').rglob('*'):
    if not f.is_file() or f.suffix not in ('.stdout', '.stderr'): continue
    total += 1
    text = f.read_text(encoding='utf-8')
    for pat in risky:
        if pat.search(text):
            leaks += 1; print(f'LEAK in {f}'); break
print(f'scanned={total}, leaks={leaks}')
"
```

`leaks=0` でなければ:
1. 即時、該当 file を **削除**
2. `src/utils/redact.py` の pattern を強化 + `tests/test_hermes_redaction.py` に新 case 追加
3. 直近全 raw_response を再 scan、`outputs/raw_responses/` 全削除を検討

### 8.6 API key を漏らさない注意 (運用全般)

- `.env` を絶対に commit しない (`.gitignore:2` で除外、`git check-ignore -v .env` で動作確認)
- `git log -p` や `git show` で `.env` の内容を表示しないこと
- API key の値を **画面録画 / スクリーンショット / Discord / Slack** に出さない
- IDE で `.env` を開いたまま画面共有しない
- `check_claude_llm.py` / `check_hermes.py` は API key を表示しない設計 (`api_key_present: True/False` のみ出力)
- 万一漏洩が発生した場合は **直ちにキーをローテーション** (Anthropic Console / xAI Console)

---

## 付録: 知っておくと便利なコマンド

| やりたいこと | コマンド |
|---|---|
| Mock で品質確認 (Claude API token 節約) | `python scripts\run_daily.py --provider mock --llm-provider claude --topic <topic>` |
| LLM も mock (API token ゼロ) | `python scripts\run_daily.py --provider mock --llm-provider mock --topic <topic>` |
| 完全 dry-run (出力書かない、manifest preview だけ) | `--dry-run` を追加 |
| LLM 強制 mock | `--no-llm` を追加 |
| pytest 全件 | `python -m pytest -p no:cacheprovider` |
| live integration test | `HERMES_LIVE_TESTS=1 python -m pytest -m hermes_live -p no:cacheprovider` |
