# future_features.md — Roadmap (not implemented yet)

> 本書は X Intelligence の **将来機能の設計メモ + TODO 管理**。
> ここに記載があっても実装はされていない。実装着手時は別途 PR / commit。
> 自動投稿しない方針は恒久維持。Analytics 連携も「投稿はしない、結果だけ
> 読む」という分離原則で設計する。

## 1. Date range support (期間指定での検索)

### 動機

現状 `--time-range` は 24h / 3d / 7d の 3 択。柴田さんは UI で 1 週間 /
1 か月の幅で検索したいケースがある。

### 設計検討

| 期間 | 推奨ステータス | 理由 |
|---|---|---|
| Today (24h) | 🟢 default | 現状実装通り、コスト低、ノイズ少 |
| Last 7 days | 🟢 許可 | Hermes prompt の "last 7 days" を変更するだけで実装可、コスト微増 |
| Last 30 days | 🟡 warning 表示 | 結果件数が増えてサマリ品質低下、API token cost x3-5、timeout リスク |
| Custom range > 30 days | 🔴 初期非推奨 | UI で警告 + 件数上限を強制 |

### Hermes 側への伝達方法

現在 Hermes adapter は `time_range` 文字列を **受け取るだけで Hermes prompt
には織り込んでいない**。Date range を活かすには:

- Option A: `DEFAULT_CITATION_CONSTRAINT` に "in the last <N> days" 文を
  動的に挿入
- Option B: `--toolsets x_search` の query 自体に "since:YYYY-MM-DD" を append
  (xAI x_search が解釈するか要 probe)
- Option C: 期間を分割して N 回 query 発射 (実装複雑、token cost 線形増加)

→ **Option A が最小実装**。Hermes adapter の `citation_constraint` に
時刻ヒントを差し込む形で対応する。

### 制約 (実装時に必須)

- default は 24h を維持
- Last 7 days までは無警告
- Last 30 days は UI で 🟡 warning 表示
- > 30 days は実装段階では明示的に reject
- 期間が長い場合は cited_urls の最大件数を絞る (現在は無制限)
- UI 上にコスト・ノイズ増加注意を表示

### UI 案 (実装時)

```
Date mode: [○ Today  ○ Last 7 days  ○ Last 30 days  ○ Custom range]
[Custom range の場合のみ] from: ___  to: ___
⚠ 30 days を超える場合は warning が出ます
```

### 想定工数: 2-3 時間 (Hermes adapter + run_daily.py + UI + tests)


## 2. Post Performance Analytics / Content Learning Loop

### 動機

現状の UI は「投稿前」のレビューに特化していて、**投稿後の結果が反映されない**。
柴田さんは:

- どの投稿が良かったか
- なぜ良かったか
- その学びを次回の投稿案に反映したい

を実現したい。投稿して終わりではなく、**post → measure → learn → improve**
のループにしたい。

### 想定アーキテクチャ (4 agent)

```
                    ┌────────────────────────────────────────┐
                    │  Streamlit Review Console (現状)         │
                    │  → approved/ に手動移動                  │
                    │  → 人間が X / Note / LinkedIn に投稿     │
                    └─────────────────┬──────────────────────┘
                                      │ 人間が外部に投稿
                                      ▼
                    ┌────────────────────────────────────────┐
                    │ [Future] Analytics Collector Agent     │
                    │  - X Analytics API / scraper           │
                    │  - 投稿の impression / engagement を取得│
                    │  - outputs/analytics/<date>/<id>.json   │
                    └─────────────────┬──────────────────────┘
                                      ▼
                    ┌────────────────────────────────────────┐
                    │ [Future] Performance Analyst Agent     │
                    │  - 高反応投稿 vs 低反応投稿の差分分析    │
                    │  - hook / topic / source / time-of-day  │
                    │  - outputs/learning_log/<date>.json     │
                    └─────────────────┬──────────────────────┘
                                      ▼
                    ┌────────────────────────────────────────┐
                    │ [Future] Content Strategy Agent        │
                    │  - 次回投稿向けの改善ルール案を生成      │
                    │  - config/content_strategy.yaml に蓄積  │
                    └─────────────────┬──────────────────────┘
                                      ▼
                    ┌────────────────────────────────────────┐
                    │ [Future] Prompt Optimizer Agent        │
                    │  - DEFAULT_CITATION_CONSTRAINT 改善案    │
                    │  - profile.yaml の atom 追加提案         │
                    │  - TOPIC_PROMPT_OVERRIDES 新規追加提案   │
                    │  - 提案は **人間レビュー必須**           │
                    └────────────────────────────────────────┘
                                      ▲
                                      │ 採用判定は柴田さん
                                      │
                    ┌────────────────────────────────────────┐
                    │ Streamlit Review Console (拡張)        │
                    │  - 投稿成績 dashboard                   │
                    │  - 学習ルール採用 yes/no                 │
                    └────────────────────────────────────────┘
```

### 想定保存先

```
outputs/
├── analytics/                    ← 新規
│   ├── <date>/
│   │   └── <post_id>.json        ← X API / scraper 由来の生データ
│   └── _index.jsonl              ← 全投稿の sumary
├── learning_log/                 ← 新規
│   └── <date>_analysis.json      ← Performance Analyst の出力
config/
└── content_strategy.yaml         ← 新規 (採用済ルールの蓄積)
```

### 評価項目 (記録対象)

- impressions
- likes
- reposts
- replies
- engagement_rate (= (likes+reposts+replies) / impressions)
- profile_clicks
- follows (この投稿経由のフォロー)
- bookmark_count
- time_to_peak (投稿〜ピーク時刻まで)
- topic
- hook_type (なぜ系 / 結論先出し / 個人エピソード / 比較表 / etc.)
- post_format (短文 / thread / 画像付き / 動画付き)
- source_type (official / founder / engineer / unknown)
- CTA 有無 (link/profile/reply に誘導)

### 保安原則 (恒久維持)

- **「投稿」は人間が手動で行う** — Analytics Collector は **読み取り専用**
- X API / scraper も読み取り権限のみ
- `tests/test_no_auto_posting_capability.py` は将来 analytics adapter にも
  適用する (scan 対象に追加)
- 学習ルールの自動適用は禁止 — 全て柴田さんが承認してから profile.yaml /
  constraint に反映

### 着手判断

X API v2 連携の方針 (free vs basic vs pro tier) と、X Analytics scraper の
規約適合性 が決まってから着手。それまでは本書に TODO として置く。

### 想定工数: 各 agent 4-8 時間、全体で 1-2 週間 (本書作成時点の estimate)


## 3. (上記以外で残っている小さな TODO)

- emerging keywords の "like" 等 residual stopword 微調整
  (今は実害なしの軽微改善)
- topic 分割 runner (`scripts/run_daily_per_topic.py`)
  - 8 topic 並列起動 + 集約 manifest を 1 コマンド化
  - 想定工数 2-3 時間
- README 軽量化 (docs/ への誘導)
  - 推定 150-170 行削減可能
- X API v2 直接連携 (`src/adapters/search_x_api.py` の本実装)
  - 上記 Post Performance Analytics の前提
- Grok Imagine 実 API 連携
  - prompt 生成までで止まっている動画/画像を実投入
