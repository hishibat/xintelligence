# X Intelligence — Claude Code 運用ガイド

このリポジトリは「mock data mode で E2E が通る」ことを最優先で設計されています。
新しい機能を足す前に、必ず `pytest -q` と `python scripts/run_daily.py --provider mock` が green であることを確認してください。

## Dual-repo セットアップ（2026-05-22〜）

このコードは **2 つの GitHub repo** にミラーされています：

| 役割 | リポジトリ | パス | 用途 |
|---|---|---|---|
| **primary**（開発） | `hishibat/company` | `Content_Production/x-intelligence/` | **commit はここで行う**。社長 workspace 全体と一緒に管理 |
| **mirror**（公開） | `hishibat/xintelligence` | root | スタンドアロン参照・将来の OSS 化候補。履歴保持で同期 |

### 同期ルール

1. **commit は必ず company 側**（`workspace/company` の `feature/content-and-tools-2026-04-04` ブランチ）で行う
2. mirror 側 (`hishibat/xintelligence`) に直接 push したり PR を出したりしない
3. **適切なタイミング**で同期スクリプトを走らせて mirror へ反映：
   - 機能 1 単位の commit が増えた時
   - PR を出す前後
   - 週次レビュー時
4. 同期コマンド（PowerShell、workspace/company のどこからでも OK）：
   ```powershell
   cd C:\Users\Hideyuki Shibata\workspace\company\Content_Production\x-intelligence
   .\scripts\sync_to_xintelligence.ps1          # 通常 push
   .\scripts\sync_to_xintelligence.ps1 -DryRun  # split のみで push しない
   ```
5. 同期後は **mirror 側の HEAD commit hash** が変わる（subtree split で再計算されるため）。同期した事実は company 側の commit message には書かなくてよい。

### 同期されないもの

- `outputs/` 配下（`.gitignore` で除外、両 repo で空）
- `Content_Production/x-intelligence/` の外側にあるファイル（`workspace/CLAUDE.md` 等）

### Troubleshoot

- `git remote 'xintelligence' is not configured` → `git remote add xintelligence https://github.com/hishibat/xintelligence.git`
- push が rejected → mirror 側に手動で commit が入っている可能性。原則 mirror は force push せず、まず `gh repo view hishibat/xintelligence` で誰が触ったか確認

## 開発原則

1. **Mock first**: 新 Provider / 新 LLM を追加するときは、まず adapter の抽象に合わせて mock で動かす。実 API は後段。
2. **欠損許容**: `StructuredPost` と `SearchCitationResult` の Union を前提に書く。`isinstance` で分岐し、`missing_fields` を必ず尊重する。
3. **Silent fallback 禁止**: LLM key が無いなどで mock に降格したら、必ず `manifest.fallback_used` と stderr warning に出す。
4. **引用元保持**: どこかで `source_urls` / `cited_urls` が落ちていないか、変更時に grep する。
5. **原文丸写し禁止**: content_generator 経由でない draft は受け付けない。`originality_note` と `needs_review` が必ずセットされる。
6. **自動投稿禁止**: どのスクリプトも投稿 API を叩かない。投稿は人間が `review_queue` から手動で出す。

## 触ってよい / よくないファイル

- ✅ `src/adapters/search_*.py` — 新 Provider 追加時
- ✅ `src/adapters/llm_*.py` — 新 LLM 追加時
- ✅ `config/*.yaml` — キーワード / トピック / プロファイル / 出力設定
- ✅ `fixtures/sample_posts.json` — mock データの追加・更新
- ⚠️ `src/core/schema.py` — スキーマ変更は影響範囲大。必ず関連テスト更新
- ❌ `outputs/` — 手動編集禁止（CI で再生成）

## 典型タスクの進め方

### 新 Provider を追加する
1. `src/adapters/search_xyz.py` を作成（`SearchProvider` を継承）
2. `Capabilities` を真実に基づいて埋める（過剰な claim 禁止）
3. `scripts/run_daily.py::_make_search_provider` に分岐追加
4. `tests/test_provider_contract.py` にケース追加
5. 実 API 呼び出しは別 PR

### スコアリング重みを変える
1. `config/output.yaml::scoring.weights` を編集
2. `tests/test_config.py::test_scoring_weights_sum_close_to_one` が通る範囲で
3. `pytest tests/test_scoring.py -q`

### 新トピックを追加
1. `config/keywords.yaml::themes` に theme block 追加
2. `config/topics.yaml::topics` に対応 topic 追加（必要なら）
3. `fixtures/sample_posts.json` に該当する mock 投稿を 2-3 件足す
4. `python scripts/run_daily.py --provider mock --topic <new_theme>`

## 失敗時のデバッグ

- `--dry-run` で出力ファイルを書かずに manifest のみ確認
- `--no-llm` で LLM を mock 固定にし、LLM-side の問題を切り分け
- `outputs/.../run_manifest.json` の `warnings` / `errors` / `fallback_used` / `missing_fields_summary` を最初に見る
