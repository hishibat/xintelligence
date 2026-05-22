# design.md — X Intelligence & Content Automation Skills

> 本書は output quality polish (commit `5d9898c`) 完了後の **設計確定版** (2026-05-22 時点)。
> `docs/design-lite.md` は MVP 立ち上げ期の軽量版で、本書がそれを supersede する。
> `docs/hermes_cli_spec.md` は Hermes CLI の実態仕様 (probe 結果)、本書からリンクされる前提資料。
>
> 歴史的参照は変更しない: 本書中の `commit c302060` は TOPIC_PROMPT_OVERRIDES 採用時点を、
> `commit 5d9898c` は output quality polish 適用時点を指す。

## 1. 全体アーキテクチャ

```
                    config/keywords.yaml         config/topics.yaml
                    config/profile.yaml          config/output.yaml
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │                  scripts/run_daily.py (orchestrator)            │
   └────┬────────────────────────────────────────────────────────────┘
        │
        ▼
   ┌────────────────────────────────────────────────────────────────┐
   │ Search Provider Adapter (src/adapters/search_*.py)             │
   │   mock | hermes | xai (stub) | x_api (stub)                    │
   │   返り値: SearchResult                                          │
   │   ├ items: list[StructuredPost | SearchCitationResult]         │
   │   ├ capabilities: Capabilities (8 bool flags)                  │
   │   ├ source_urls: list[str]                                     │
   │   ├ missing_fields: list[str]                                  │
   │   └ raw_response_path: str | None                              │
   └────┬───────────────────────────────────────────────────────────┘
        │
        ▼
   ┌────────────────────────────────────────────────────────────────┐
   │ src/core/dedupe.py        — URL + 本文ハッシュで重複排除        │
   │ src/core/verification.py  — VerificationTags 付与               │
   │ src/core/scoring.py       — 5 軸スコアリング (profile 反映)     │
   │ src/core/trend_analyzer.py — topic 別 trend summary             │
   │ src/core/content_generator.py — 4 channel draft + originality   │
   │ src/core/video_prompt_generator.py — 4 use case prompt          │
   │ src/core/manifest.py      — RunManifest 構築                    │
   └────┬───────────────────────────────────────────────────────────┘
        │ (上記が呼び出す)
        ▼
   ┌────────────────────────────────────────────────────────────────┐
   │ LLM Adapter (src/adapters/llm_*.py)                            │
   │   mock | claude | grok (stub)                                  │
   │   silent fallback 禁止: 失敗時は manifest.fallback_used 記録    │
   └────────────────────────────────────────────────────────────────┘
        │
        ▼
   ┌────────────────────────────────────────────────────────────────┐
   │ scripts/export_results.py                                      │
   │   write_daily_report_md / write_csv / write_xlsx /             │
   │   write_drafts_md / write_video_prompts_md / write_review_queue │
   └────┬───────────────────────────────────────────────────────────┘
        │
        ▼
   outputs/{daily_reports, csv, excel, content_drafts, video_prompts,
            review_queue, raw_responses}
```

## 2. Provider Adapter 構造

### 2.1 抽象クラス (`src/adapters/search_base.py`)

```python
class SearchProvider(ABC):
    name: ClassVar[str]
    capabilities: ClassVar[Capabilities]

    @abstractmethod
    def search(self, query: str, topic: str, time_range: str) -> SearchResult: ...
```

### 2.2 Capabilities フラグ (8 個)

| flag | 意味 |
|---|---|
| `supports_raw_post_text` | 投稿本文を取得できるか |
| `supports_author` | 投稿者名を取得できるか |
| `supports_created_at` | 投稿日時を取得できるか |
| `supports_engagement_metrics` | likes / reposts / replies / views を取得できるか |
| `supports_thread_context` | スレッド前後を取得できるか |
| `supports_citations` | 出典 URL を返すか |
| `supports_time_range` | 期間絞り込みを Provider 側で出来るか |
| `supports_query_operators` | クエリ演算子 (AND/OR/from: 等) を解釈するか |

### 2.3 Provider ごとの Capabilities (本書作成時点)

| flag | mock | hermes | xai (stub) | x_api (stub) |
|---|---|---|---|---|
| supports_raw_post_text | ✅ | ❌ | ❌ | ✅ |
| supports_author | ✅ | ❌ | ❌ | ✅ |
| supports_created_at | ✅ | ❌ | ❌ | ✅ |
| supports_engagement_metrics | ✅ | ❌ | ❌ | ✅ |
| supports_thread_context | ❌ | ❌ | ❌ | ✅ |
| supports_citations | ✅ | ✅ | ✅ | ❌ |
| supports_time_range | ✅ | ❌ | ❌ | ✅ |
| supports_query_operators | ✅ | ❌ | ❌ | ✅ |

> Hermes は `-z` oneshot mode で「Grok 合成テキスト + Source URLs」を返すため、投稿単位の構造化メタデータは取れない。これを正直に Capabilities に反映している。

## 3. LLM Adapter 構造

### 3.1 抽象クラス (`src/adapters/llm_base.py`)

```python
class LLMProvider(ABC):
    name: ClassVar[str]
    fallback_used: bool = False

    @abstractmethod
    def complete(self, prompt: str, *, max_tokens: int = 800,
                 temperature: float = 0.4) -> str: ...
```

### 3.2 Claude adapter (`src/adapters/llm_claude.py`) の特徴

- `claude-opus-4-7` 等の新モデルで `temperature` パラメータが deprecated → **自動で 1 回 retry**（temperature を外して再呼び出し）し、以降同セッションは `_omit_temperature=True` を保持
- API key 不在 / SDK 不在 / API 例外 → `MockLLMProvider` に fallback、`self.fallback_used = True` をセット
- `run_daily.py::_make_llm_provider` で `provider.fallback_used` を見て `warn(...)` を発射、`manifest.fallback_used` に記録

### 3.3 silent fallback 防止の経路

```
ClaudeLLMProvider.__init__()
  ├ ANTHROPIC_API_KEY なし → self.fallback_used = True
  ├ anthropic SDK なし     → self.fallback_used = True
  └ ANTHROPIC_API_KEY あり → 本物クライアント
       └ complete() 中の例外 → 1 回 retry (temperature 起因なら除外) → さらに失敗で mock fallback

scripts/run_daily.py::_make_llm_provider:
  provider = ClaudeLLMProvider()
  if provider.fallback_used:
      warn("Claude API key missing or SDK unavailable → falling back to MockLLMProvider.")
       ↓ shared warnings buffer 経由で
  manifest.warnings に格納
  manifest.fallback_used に "llm:claude->mock" を append
```

## 4. データスキーマ — StructuredPost と SearchCitationResult の違い

### 4.1 StructuredPost (X API / mock provider 由来)

```python
@dataclass
class StructuredPost:
    post_id: str
    text: str
    url: str
    provider_name: str
    author: str | None
    author_handle: str | None
    created_at: datetime | None
    metrics: dict[str, int] | None   # {"likes", "reposts", "replies", "views"}
    thread_context: list[str] | None
    topic: str | None
    verification: VerificationTags
    missing_fields: list[str]
    kind: Literal["structured_post"]
```

- 1 件 = 1 投稿、投稿 ID と URL が必ずある
- engagement metrics があれば scoring の `importance` を直接計算
- mock は fixtures から、X API は API v2 レスポンスから生成

### 4.2 SearchCitationResult (Hermes / xAI Responses 由来)

```python
@dataclass
class SearchCitationResult:
    summary: str                              # LLM の合成応答テキスト
    provider_name: str
    cited_urls: list[str]                     # x.com/twitter.com の status URL
    cited_posts: list[dict[str, Any]]         # {"url", "snippet", "title"} の dict 列
    provider_response: str                    # LLM の応答そのもの
    confidence: float | None
    topic: str | None
    verification: VerificationTags
    missing_fields: list[str]
    parse_warnings: list[str]                 # 例: "no x.com URLs found"
    raw_response_path: str | None             # outputs/raw_responses/.../<id>.stdout
    kind: Literal["search_citation_result"]
```

- 1 件 = 1 クエリへの合成回答（複数の引用 URL を内包しうる）
- engagement metrics は取れない → `missing_fields` に必ず 6 項目 (author / author_handle / created_at / engagement_metrics / thread_context / raw_post_text) を入れる
- scoring の `importance` は `citation_fallback` 経路で計算（citation_count × 2.5 + confidence × 10）

### 4.3 違いまとめ

| 項目 | StructuredPost | SearchCitationResult |
|---|---|---|
| 1 件の単位 | 1 投稿 | 1 クエリへの合成回答 |
| post_id | あり | なし |
| author | あり | なし (missing_fields に必ず) |
| created_at | あり | なし |
| engagement metrics | あり (mock/x_api) | なし |
| URL | 1 件 (`url`) | 複数 (`cited_urls`) |
| scoring method | `full` | `citation_fallback` |
| parse_warnings | なし | あり（URL 欠落等の signal） |
| 主な provider | mock / x_api | hermes / xai |

両者は `Post = StructuredPost | SearchCitationResult` という Union 型で扱われる。downstream (scoring / drafts / video prompts) は `isinstance` 分岐で対応。

## 5. Hermes Adapter 設計

### 5.1 呼び出し形式

```python
cmd = ["wsl", "bash", "-lc",
       f"hermes -z {shlex.quote(full_query)} -t x_search"]
```

`-z, --oneshot`: stdout に **最終応答テキストのみ** を出す Hermes top-level flag。
verbose log や tool preview の mix がないため parse が単純。

詳細は [`docs/hermes_cli_spec.md`](./hermes_cli_spec.md) を参照。

### 5.2 prompt 構築

```python
full_query = (
    query.rstrip()                                          # ユーザー query 本体
    + self.citation_constraint                              # DEFAULT_CITATION_CONSTRAINT
    + TOPIC_PROMPT_OVERRIDES.get(topic, "")                 # topic 別 addendum
).strip()
```

`DEFAULT_CITATION_CONSTRAINT` には:
- `x_search` を必ず呼ぶ指示
- Sources block 形式 (`https://x.com/<handle>/status/<id>`) の厳格化
- 関係する X 投稿がない時の `Sources: none found` 形式

`TOPIC_PROMPT_OVERRIDES` (本書作成時点 `grok_xai` のみ) には:
- self-referential 抑止 (model-agnostic 表現)
- 優先 source 順序 (xai 公式 → 創業者 → engineer → user)
- internal knowledge から答えることを明示禁止

### 5.3 redaction

- subprocess の `stdout` / `stderr` は `src/utils/redact.py::redact()` を **必ず通してから** 永続化
- 検出 pattern (sk-/xai-/JWT/Bearer/Using API key/api_key=/cookie/password/URL query token)
- `is_safe()` で leak detector も提供、preview 表示時の最終チェックに使用

### 5.4 raw_response 保存

```
outputs/raw_responses/hermes/<YYYY-MM-DD>/
  <HHMMSS>_<topic>_<query_hash8>.stdout    # redact 済 stdout
  <HHMMSS>_<topic>_<query_hash8>.stderr    # redact 済 stderr
  <HHMMSS>_<topic>_<query_hash8>.meta.json # cmd, return_code, elapsed_ms, query_preview
```

`.gitignore` で `outputs/raw_responses/` を除外。`outputs/hermes_probe/` も同様。

### 5.5 fallback policy

| `--search-fallback` | Hermes 成功 | Hermes 失敗 |
|---|---|---|
| `none` (default) | exit 0、`fallback_used=[]` | **exit non-zero (4)**、部分書き込みなし |
| `mock` | exit 0、`fallback_used=[]` | exit 0、`fallback_used=["search:hermes->mock"]`、warning 必須記録 |

silent fallback は **常に禁止**。`fallback` 引数を `None` にした場合は `HermesError` raise、`MockSearchProvider` を inject した場合は降格して manifest に記録。

## 6. Citation 品質シグナル

### 6.1 計算ロジック (`src/core/manifest.py::summarize_citationless`)

```python
def summarize_citationless(items, *, high_ratio_threshold=0.5):
    citationless = [p for p in items if not p.citation_urls()]
    count = len(citationless)
    ratio = count / len(items) if items else 0.0
    # topic 別: そのtopic 内の citationless 件数 / 全件数 > 0.5 なら flag
    ...
    return count, ratio, sorted(high_ratio_topics)
```

`Post.citation_urls()` は:
- `StructuredPost`: `[self.url]` または `[]`
- `SearchCitationResult`: `list(self.cited_urls)`

### 6.2 manifest フィールド

```json
{
  ...
  "citationless_items_count": 1,
  "citationless_ratio": 0.333,
  "topics_with_high_citationless_ratio": []
}
```

### 6.3 report.md 表示

`scripts/export_results.py::write_daily_report_md` 内で:

| ratio | emoji | 意味 |
|---|---|---|
| `< 0.20` | 🟢 | 健全 |
| `0.20-0.50` (excl) | 🟡 | 要観察 |
| `≥ 0.50` | 🔴 | 該当 topic だけ prompt 強化 / 再実行検討 |

加えて、50% 超の topic は `🔴 topics_with_high_citationless_ratio: <name>` で個別 flag。

## 7. Topic-specific prompt override (grok_xai のみ)

### 7.1 なぜ grok_xai だけか

C-1 mid-scope IV (commit `9261354` 後) で:
- `hermes_openclaw`: 0/3 citationless (0%)
- `ai_agent`: 1/5 citationless (20%)
- `grok_xai`: **4/5 citationless (80%)** 🔴

3 topic 同時実行で **grok_xai のみ突出**。Grok が自分自身に関する質問 (`Grok`, `xAI`, `Grok Imagine`, etc.) で `x_search` を呼ばずに internal knowledge から直接答えてしまう傾向と判断。

DEFAULT_CITATION_CONSTRAINT への一般的な「x_search 必ず呼べ」追加 (commit `52a5986`) では 60% までしか改善せず、目標 40% に届かなかった。

→ **grok_xai だけに self-referential 抑止の追加 prompt を当てる** topic-specific override 方式を採用 (commit `c302060`)。3-run mean で **35%** に改善し、目標達成。

### 7.2 採用基準

新たに `TOPIC_PROMPT_OVERRIDES` に entry を追加する判定基準:
- 該当 topic で `topics_with_high_citationless_ratio` フラグが 3 run 中 2 回以上立つ
- かつ DEFAULT_CITATION_CONSTRAINT 改善で対応できる範囲を超えている
- かつ override 追加で他 topic に副作用がないことを 1 run で確認

### 7.3 model-agnostic 設計

override 文言は `"The selected model may have internal knowledge..."` 形式で、将来 Grok 以外のモデルに切替えた時も意味が通るよう設計。`"You are Grok"` のような model-specific な表現は使わない。

## 8. RunManifest 設計

### 8.1 全フィールド

```python
@dataclass
class RunManifest:
    # 識別
    run_id: str                                    # YYYYMMDDTHHMMSSZ-<uuid8>
    executed_at: datetime
    provider: str                                  # mock / hermes / xai / x_api
    llm_provider: str                              # mock / claude / grok
    # 再現性
    config_hash: str                               # configs + fixtures の sha256[:16]
    fixture_hash: str                              # fixtures 単独の sha256[:16]
    # データボリューム
    query_count: int
    raw_item_count: int
    deduped_item_count: int
    top10_count: int
    missing_fields_summary: dict[str, int]
    # 健全性 (silent fallback 防止)
    warnings: list[str]
    errors: list[str]
    fallback_used: list[str]                       # e.g. ["search:hermes->mock", "llm:claude->mock"]
    # 品質シグナル
    citationless_items_count: int
    citationless_ratio: float
    topics_with_high_citationless_ratio: list[str]
```

### 8.2 設計原則

- **silent fallback 禁止**: fallback を発火させた経路は必ず `fallback_used` に append
- **secret 非格納**: フィールド名と値の両方で API key / token 系を持たない（`tests/test_no_secret_in_manifest.py` で検証）
- **再現可能性**: 同じ config + fixtures (mock の場合) で同じ `config_hash` / `fixture_hash` が出る
- **品質シグナルは run の主成果物として manifest と report.md の両方に出す**

## 9. Secret hygiene 設計

### 9.1 多層防御の構成

```
[Layer 1] .env (gitignore で除外、git status に出ない)
   ↓ load_dotenv(override=True) — shell の空 placeholder に勝つ
[Layer 2] ClaudeLLMProvider が os.environ から読み、self.api_key に保持
   ↓ subprocess.run() のときに wsl bash -lc 経由 (CLI 自管理)
[Layer 3] Hermes CLI 側 (~/.hermes/.env) — 本プロジェクトは触らない
   ↓ subprocess stdout/stderr が返る
[Layer 4] src/utils/redact.py::redact() を必ず通す
   ↓ 永続化前にマスク (sk- / xai- / JWT / Bearer / Using API key / api_key= 等)
[Layer 5] outputs/raw_responses/ は gitignore で除外
[Layer 6] tests/test_no_secret_in_manifest.py で RunManifest フィールド名検査
[Layer 7] tests/test_hermes_redaction.py で 13 pattern 全件マスク検証
```

### 9.2 `load_dotenv(override=True)` の理由

外側 shell (PowerShell や Claude Code harness) が `ANTHROPIC_API_KEY=""` のような **空 placeholder を export** していると、`override=False` だと dotenv が「既に set 済」と判断して `.env` の実値で上書きせず、silent fallback してしまう。

これを防ぐため `src/utils/config_loader.py::load_config` で `override=True` を明示。`.env` を真値として優先する。経緯は commit `34becee` 参照。

## 10. 自動投稿禁止テストの考え方

`tests/test_no_auto_posting_capability.py` は **3 層 + 2 ガード** で自動投稿を構造的に不可能にする:

| 検査対象 | 検査内容 |
|---|---|
| **L1: 関数定義** | `def\s+(post_to_x\|send_tweet\|tweet\|publish_post\|create_tweet\|create_post)\b` 等を src/ + scripts/ 全 .py で grep |
| **L2: import** | `tweepy` / `python_twitter` / `twython` / `linkedin_api` 等の投稿 SDK を import していないか |
| **L3: 呼び出し方** | `\.post\(.*tweets.*\)` / `requests\.post\(.*twitter\.com\)` / `\.create_tweet\(` 等の write-style call を grep |
| **L3': URL** | `api.twitter.com/2/tweets/manage` / `linkedin.com/v2/posts` / `api.linkedin.com/v2/ugcPosts` 等の write endpoint を grep |
| **G1: requirements.txt** | `tweepy` / `python-twitter` / `twython` / `linkedin-api` を pin していないか |
| **G2: README.md** | "draft generation only" / "投稿実行機能なし" / "自動投稿は実装しない" のいずれかのマーカーが存在 |

parametrize で **src/ + scripts/ 配下の全 .py** をスキャン。万一誰かが将来「投稿関数を追加してしまった」場合、pytest が即時 fail。

新 endpoint や新 SDK が現れたら、このテストにパターンを追加する。

## 11. Output quality polish 設計 (commit `5d9898c`)

E2E 出力レビューで判明した artifact-level の品質課題 5 件を一括解消した
polish 系の改修。コア機能（Adapter / scoring / fallback policy）には触らず、
**出力品質と運用フィードバック性** だけを改善した。

### 11.1 公式アカウント自動 promotion

問題: Hermes 由来の `SearchCitationResult` はデフォルトで `source_type="unknown"`。
NousResearch や AnthropicAI など公式アカウント由来の citation でも `unverified`
扱いになり、投稿前 fact-check の優先順位判定が手動になっていた。

解決: `config/official_handles.yaml` (新設) で 22 handles を 5 階層に登録し、
`verification.tag_items()` の入口で URL から handle を抽出して階層 lookup を
実施、`source_type` を promotion してから既存の `_classify_status` に渡す。

階層 (高→低 の優先順位):

| 階層 | 例 |
|---|---|
| `official` | NousResearch / xai / AnthropicAI / OpenAI / GoogleDeepMind / awscloud / Microsoft / databricks / SnowflakeDB / NVIDIA / OpenClaw / EUAIOffice / StanfordHAI 等 |
| `founder_executive` | elonmusk / sama / satyanadella / demishassabis / dario_amodei / jensenhuang / karpathy |
| `engineer_dev` | simonw / jayalammar / bcherny / grimalkina / schneierblog |
| `media` | gartner_inc 等 |
| `influencer` | linusekenstam 等 |

実装: `src/core/verification.py`
- `_HANDLE_FROM_URL`: `x.com/<handle>/status/...` から handle 抽出
- `_build_handle_index`: 階層別 dict から flat lookup を構築 (重複は上位階層が勝つ)
- `_resolve_source_type`: item の citations 全部を見て最強階層を返す
- `tag_items()` に `official_handles` 引数追加、promotion → classify の順で適用

注意: Grok が生成する `x.com/i/status/<id>` 形式の匿名 URL は handle が露出
しないため promotion されない。`≥ 2 citations` あれば
`verification_status = multi_source_confirmed` で「複数源裏取り済」相当に
格上げされる。

### 11.2 Content draft 末尾完結チェック

問題: LinkedIn など長文 channel で `max_tokens` を超えると mid-sentence
で切れることがあった。検知できないと投稿前レビューで時間ロス。

解決: `src/core/content_generator.py::_looks_complete()` を新設。末尾の
non-whitespace char が sentence terminator (`. 。 ! ? ！ ？ ) — " 、`)
でない場合は `originality_note` に `[WARNING] draft may be truncated`
を append。LinkedIn の `max_tokens` も `1200 → 1600` (35% headroom) に拡張。

### 11.3 Emerging keywords ノイズ除去

問題: `report.md` の `emerging` keywords に `https / posts / describe / share`
等の URL 断片や一般動詞が leak していた。

解決: `src/core/trend_analyzer.py::_STOP` を大幅拡張 (URL 系 + 一般動詞 +
一般名詞)、`_URL_FRAGMENT` regex で url 系 token を別途 reject、純数字 token
も除外。

### 11.4 note_outline 重複出力削除

問題: `03_note_outline.md` で `## draft_text` と後段の
`## note_title_candidates` / `## note_outline` が三重出力されていた。

解決: `scripts/export_results.py::write_drafts_md` から append セクションを
削除。`ContentDraft` dataclass の構造化フィールドはプログラム的アクセス用
として残置。

### 11.5 openpyxl エラーの明示化

問題: 環境セットアップミスで `ModuleNotFoundError: No module named 'openpyxl'`
が出ても原因が分かりづらい。

解決: `scripts/export_results.py::write_xlsx` の冒頭で `ImportError` を捕捉
し、`RuntimeError` として `pip install -r requirements.txt` を案内する明示
メッセージに置換。
