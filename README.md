# TOEIC TTS - Part 3 / Part 4 Listening Practice Generator

[![GitHub stars](https://img.shields.io/github/stars/masanao-ohba/toeic-tts?style=social)](https://github.com/masanao-ohba/toeic-tts/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/masanao-ohba/toeic-tts?style=social)](https://github.com/masanao-ohba/toeic-tts/network/members)
[![GitHub issues](https://img.shields.io/github/issues/masanao-ohba/toeic-tts)](https://github.com/masanao-ohba/toeic-tts/issues)
[![GitHub license](https://img.shields.io/github/license/masanao-ohba/toeic-tts)](https://github.com/masanao-ohba/toeic-tts/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![OpenAI](https://img.shields.io/badge/OpenAI-gpt--4o--mini--tts-green)](https://platform.openai.com/docs/guides/text-to-speech)

OpenAI `gpt-4o-mini-tts` を使って、TOEIC **Part 3（会話）/ Part 4（説明文）** の
フル音声（先読み設問 → 本文 → 設問+選択肢 → 正解）を自動生成する CLI ツールです。

## Features

- **Part 3 / Part 4 両対応** — CLI または設定ファイルで切替
- **2段階の難易度** — `intermediate` / `advanced`
- **3設問 × 4選択肢 + 正解ラベル** を LLM に構造化生成させる
- **9セクション固定レイアウト** で音声を結合（先読み → 短ポーズ 1500ms → 本文 → 短ポーズ 1500ms → 設問+選択肢 → 長ポーズ 8000ms → 正解 → 短ポーズ 1500ms → Key phrases）
- **正解読み上げは `Number one. <正解選択肢の本文>.` 形式**（A/B/C/D ラベルは読まない）
- **Key phrases セクション**：本文中の TOEIC 頻出表現を 3〜8 個、英日対訳で末尾にまとめて読み上げ
- **TOEIC 頻出語彙・ひっかけパターン**（paraphrase / 時制混同 / 部分一致 / 語彙連想）をプロンプトで明示注入
- WAV / MP3 出力

## Project Structure

```
toeic-tts/
├── main.py                          # 一括実行（transcript生成 → 音声合成）
├── generator/
│   ├── transcript.py                # Part 3/4 transcript 生成
│   └── tts.py                       # sections[] → 音声合成
├── examples/
│   ├── part3_sample_config.json
│   └── part4_sample_config.json
├── transcripts/                     # transcript JSON
├── output/                          # 音声出力（gitignore 推奨）
├── pyproject.toml
└── .env                             # OPENAI_API_KEY
```

## Prerequisites

- Python 3.8+
- [uv](https://docs.astral.sh/uv/)
- OpenAI API キー

## Setup

```bash
git clone git@github.com:masanao-ohba/toeic-tts.git
cd toeic-tts
uv sync
echo 'OPENAI_API_KEY=sk-proj-your-key-here' > .env
```

## Usage

### 1. 一括実行（CLI）

```bash
# Part 3（会話、intermediate）
uv run python main.py --part 3 --topic "office relocation"

# Part 3、3名、advanced
uv run python main.py --part 3 --speakers 3 --difficulty advanced --topic "quarterly projections"

# Part 4（ナレーション）
uv run python main.py --part 4 --topic "company-wide announcement about parking policy"
```

### 2. 設定ファイル（JSON）から実行

```bash
uv run python main.py --config examples/part3_sample_config.json
uv run python main.py --config examples/part4_sample_config.json
```

CLI フラグは設定ファイルの値を上書きします。例:

```bash
uv run python main.py --config examples/part3_sample_config.json --difficulty advanced
```

## Audio Layout

最終的な音声は以下の 9 パート構成で出力されます:

| # | 内容 | ポーズ |
|---|------|--------|
| 1 | Question 1-3 の stem 先読み（選択肢なし） | 各問間 600ms |
| 2 | (短ポーズ) | **1500ms** |
| 3 | 本文（Part 3: 会話 / Part 4: 説明文） | 行間 450ms |
| 4 | (短ポーズ) | **1500ms** |
| 5 | Question 1-3 + 選択肢 A/B/C/D 読み上げ | 選択肢間 400ms / 問間 600ms |
| 6 | (長ポーズ — 受験者が回答する時間) | **8000ms** |
| 7 | "Number one. <正解選択肢の本文>." × 3 | 問間 700ms |
| 8 | (短ポーズ) | **1500ms** |
| 9 | "Key phrases." → 各 key_phrase（英→日）× 3〜8 | エントリ間 800ms |

短ポーズ 1500ms と長ポーズ 8000ms は仕様上の**固定値**です。

## Transcript JSON Schema

```json
{
  "title": "Office Relocation Discussion",
  "slug": "office_relocation_discussion",
  "part": 3,
  "difficulty": "intermediate",
  "speakers": {
    "W1": { "voice": "marin", "speed": 0.96, "instructions": "..." },
    "M":  { "voice": "cedar", "speed": 0.98, "instructions": "..." },
    "W2": { "voice": "shimmer", "speed": 0.97, "instructions": "..." },
    "N":  { "voice": "ash", "speed": 0.97, "instructions": "TOEIC narrator..." }
  },
  "questions": [
    {
      "id": 1,
      "text": "What are the speakers mainly discussing?",
      "choices": {
        "A": "A software upgrade",
        "B": "An office relocation",
        "C": "A client presentation",
        "D": "A hiring decision"
      },
      "answer": "B"
    }
  ],
  "key_phrases": [
    { "en": "office relocation", "ja": "オフィス移転" },
    { "en": "on short notice",   "ja": "急な通知で" },
    { "en": "follow up with",    "ja": "追って連絡する" }
  ],
  "sections": [
    { "type": "preview_questions",     "lines": [ { "speaker": "N", "text": "Question 1. ...", "pause_ms_after": 600 } ] },
    { "type": "passage",               "lines": [ { "speaker": "W1", "text": "...", "pause_ms_after": 450 } ] },
    { "type": "questions_with_choices","lines": [ { "speaker": "N", "text": "Question 1. ...", "pause_ms_after": 400 } ] },
    { "type": "answers",               "lines": [ { "speaker": "N", "text": "Number one. An office relocation.", "pause_ms_after": 700 } ] },
    { "type": "key_phrases",           "lines": [ { "speaker": "N", "text": "Key phrases.", "pause_ms_after": 500 }, { "speaker": "N", "text": "office relocation. オフィス移転。", "pause_ms_after": 800 } ] }
  ]
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `title` | string | Yes | タイトル |
| `slug` | string | No | ファイル名に使われる |
| `part` | 3 \| 4 | Yes | TOEIC パート指定 |
| `difficulty` | "intermediate" \| "advanced" | Yes | 難易度ラベル |
| `speakers.<id>` | object | Yes | `voice`, `speed`, `instructions` |
| `questions[]` | array | Yes | 3 問。`id`, `text`, `choices {A,B,C,D}`, `answer` |
| `key_phrases[]` | array | Yes (新規生成時) | 3〜8 件。各要素は `{en, ja}` の英日対訳。範囲外は `ValueError` |
| `sections[]` | array | Yes | 5 セクション: `preview_questions` / `passage` / `questions_with_choices` / `answers` / `key_phrases` |
| `sections[].lines[].pause_ms_after` | int | No | 行直後のポーズ（セクション末尾は TTS 側が 1500/8000ms で上書き） |

## CLI Options (main.py)

```
usage: main.py [-h] [--config CONFIG] [--part {3,4}]
               [--difficulty {intermediate,advanced}] [--topic TOPIC]
               [--speakers {1,2,3}] [--turns TURNS]
               [--chat-model CHAT_MODEL] [--tts-model TTS_MODEL]
               [--speed SPEED] [--output-format {wav,mp3}]
               [--mp3-bitrate {128k,256k}]
               [--transcript-dir TRANSCRIPT_DIR] [--audio-dir AUDIO_DIR]
```

- `--part` と `--topic` は必須（設定ファイルで指定してもよい）
- Part 4 指定時は `--speakers` は 1 に強制されます
- Part 3 指定時は `--speakers` は 2 または 3（デフォルト 2）
- CLI フラグは設定ファイルを上書きします

## License

[MIT](LICENSE)
