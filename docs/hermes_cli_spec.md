# Hermes CLI 実態仕様 (probe 2026-05-21)

Step 0 probe で確定した、`search_hermes.py` 実装の前提となる仕様。
柴田さん環境 (Windows + WSL2 Ubuntu) で `hermes 0.14.0` (`hermes-agent 0.14.0`,
v2026.5.16 release line) を probe。

## 1. インストール / 起動

| 項目 | 値 |
|---|---|
| 公式 install | `curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh \| bash` (WSL2 Ubuntu 推奨) |
| CLI バイナリ | `~/.local/bin/hermes` (PATH 上) |
| Python venv | `~/.hermes/venv/bin/hermes` (entry point) |
| Auth ストレージ | `~/.hermes/.env` および `~/.hermes/config.yaml` |
| Sessions ストレージ | `~/.hermes/state.db` (SQLite) |
| 検証コマンド | `hermes doctor` |
| バージョン取得 | `hermes --version` または `hermes version` |

## 2. v0.2 想定との差分 (全部書き直し)

| 項目 | v0.2 想定 | 実態 |
|---|---|---|
| 単発呼び出し | `hermes prompt --tool x_search "Q"` | `hermes -z "Q" -t x_search` (top-level) または `hermes chat -q "Q" -t x_search -Q` |
| JSON 出力 flag | `--json` | **存在しない**。`-z` (oneshot) で**最終応答テキストのみ** を stdout に出す設計 |
| 認証コマンド | `hermes auth login` | `hermes login`（top-level）、または `hermes auth add <provider>` (pool 管理) |
| 認証状態確認 | `hermes auth status` | `hermes doctor` の "◆ Auth Providers" セクション、または `hermes status` |
| ツール一覧 | `hermes tools list` | `hermes tools list` (同じ)、または `hermes doctor` の "◆ Tool Availability" |
| ツール有効化 | `hermes tools enable x_search` | `hermes tools enable x_search` (同じ)、ただし**デフォルトで有効**なケースが多い |
| 主要モデル選択 | `hermes models list` | `hermes model` (対話的 picker)、または `--model anthropic/claude-sonnet-4.6` で per-call 上書き |

## 3. 最適呼び出し形式 (確定)

### 単発検索 (pipeline 用 = 我々の用途)

```bash
hermes -z "<query>" -t x_search
```

`-z, --oneshot`:
> "send a single prompt and print **ONLY the final response text** to stdout.
> No banner, no spinner, no tool previews, no session_id line. Tools, memory,
> rules, and AGENTS.md in the CWD are loaded as normal; approvals are
> auto-bypassed. Intended for scripts / pipes."

`-t TOOLSETS, --toolsets`:
> Comma-separated toolsets to enable for this invocation. Applies to
> `-z/--oneshot` and `--tui`.

→ stdout = 純粋に Grok/Claude の合成応答テキスト。stderr = 通常は空。

### モデル / プロバイダ強制 (将来オプション)

```bash
hermes -z "<query>" -t x_search --model xai/grok-4.3 --provider xai-oauth
```

## 4. 出力スキーマ (実測)

### stdout (smoke test 実測)

```
A recent X post describes Claude Code running in full agent mode for
autonomous 2026 workflows handling research, coding, testing and deployment
loops with full-stack capabilities. It emphasizes tool use, memory management
and sub-agents while seeking new project ideas.
Sources: https://x.com/i/status/2056482709548249230
```

- フォーマット: **自由形式の自然言語応答**。マークダウンも JSON も保証なし
- Source URLs: プロンプトで明示すれば `Sources:` 行 / 本文中 / `[1]` 注釈 のいずれかで返る
- URL パターン: `https://x.com/i/status/<digits>`、`https://x.com/<handle>/status/<digits>`、稀に短縮 (`t.co/...`)

### stderr

- 通常 = **空** (`-z` モードは TTY 用 progress を吐かない)
- エラー時 = Python traceback / "Error: ..." 行が出る (要捕捉)

### 終了コード

- 0 = 成功（応答が空でも 0 を返す可能性 — 要 stdout 長さチェック）
- 非 0 = CLI レベル失敗（auth 切れ、tool 未有効、quota 超過、Python 例外など）

## 5. `hermes doctor` の parseable 項目

| セクションヘッダ | 抽出ロジック |
|---|---|
| `◆ Auth Providers` | `✓ xAI OAuth (logged in)` のように `✓` + provider 名 + `(logged in)` を grep |
| `◆ Tool Availability` | `✓ x_search` 行を grep。`✓` で有効、`⚠` で無効 |
| `◆ Configuration Files` | `✓ ~/.hermes/.env file exists` 等 |
| `◆ Required Packages` | `✓ OpenAI SDK` 等。我々は読まなくて良い |

`check_hermes.py` はこの `hermes doctor` 出力を grep ベースで検証する。

## 6. 認証情報 (重要: redaction 対象)

| 場所 | 内容 | 我々のコードが触るか |
|---|---|---|
| `~/.hermes/.env` | API keys (OpenAI, xAI, Anthropic 等) | **NO**。Hermes CLI が自管理 |
| `~/.hermes/config.yaml` | Provider 設定、preferred model | **NO** |
| `~/.hermes/state.db` | session 履歴 | **NO** |
| stdout 出力 | 通常はキー漏れなし (`-z` mode は redacted) | redact ON で念のため通す |
| stderr (エラー時) | traceback に Authorization ヘッダが混入する可能性 | **必ず redact** |
| `hermes --verbose` の log | `Using API key: <value>` 行が出ることがある (柴田さん事前確認) | 我々は `-z` を使うので回避 |

## 7. Toolsets と x_search

`hermes doctor` 実測:
```
◆ Tool Availability
  ✓ x_search                     ← 我々が使う
  ✓ browser, terminal, file, ...
  ⚠ web (missing EXA_API_KEY ...)
```

- `x_search` は **xAI OAuth ログイン済の場合に有効化される** (xAI 提供の検索 tool を Grok 4.x 経由で呼ぶ)
- 柴田さん環境では既に有効
- `--toolsets x_search` で他のツールを load せず x_search のみに絞ると、出力がより検索結果に集中する

## 8. 既知の制約 / 注意事項

| 項目 | 内容 |
|---|---|
| Rate limit | x_search は xAI 側の rate limit に依存。詳細不明 → 1 query/sec で開始して様子見、429 受けたら 30s wait |
| Cost | 1 call ≈ Grok 4.x の通常 chat + x_search tool call cost。X Premium+ subscription があれば includes |
| プロンプト依存 | Source URLs を引き出すには `End with: Sources: <url>` のような明示指示が必要 |
| timeout | デフォルトは無制限。subprocess 側で 60-120 秒の hard timeout を設けるべき |
| Non-determinism | 同じ query でも response 文言・URL 数は run ごとに揺れる |
| 出力エンコーディング | UTF-8 (LF line ending、`-z` モード) |

## 9. 我々の adapter からの呼び出し設計 (確定)

```python
# 概要 (実装は v0.3 plan の後)
cmd = [
    "wsl",                      # Windows 側 Python から WSL2 へ
    "bash", "-lc",
    f"hermes -z {shlex.quote(query_with_citation_instruction)} -t x_search",
]
result = subprocess.run(cmd, capture_output=True, timeout=120, text=True, encoding="utf-8")

stdout = redact(result.stdout)
stderr = redact(result.stderr)

# stdout から URL 抽出
urls = re.findall(r"https://x\.com/(?:i/status/|[^/\s]+/status/)\d+", stdout)
```

## 10. probe で得た成果物 (gitignore 対象)

`outputs/hermes_probe/` 配下 (commit しない):

```
__help.stdout       155 lines   全 hermes サブコマンド一覧
doctor.stdout       117 lines   Auth Providers + Tool Availability
chat___help.stdout   59 lines   `hermes chat` 詳細
tools___help.stdout  16 lines   `hermes tools` 詳細
sessions___help.stdout  17 lines
smoke_z.stdout       2 lines    `hermes -z "..." -t x_search` 実応答
smoke_z.stderr       0 lines    空
```

すべて `scripts/_redact.py` を通過済み。
