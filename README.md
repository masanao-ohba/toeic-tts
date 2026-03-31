# TOEIC TTS - Multi-Speaker Dialogue Audio Generator

[![GitHub stars](https://img.shields.io/github/stars/masanao-ohba/toeic-tts?style=social)](https://github.com/masanao-ohba/toeic-tts/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/masanao-ohba/toeic-tts?style=social)](https://github.com/masanao-ohba/toeic-tts/network/members)
[![GitHub issues](https://img.shields.io/github/issues/masanao-ohba/toeic-tts)](https://github.com/masanao-ohba/toeic-tts/issues)
[![GitHub license](https://img.shields.io/github/license/masanao-ohba/toeic-tts)](https://github.com/masanao-ohba/toeic-tts/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![OpenAI](https://img.shields.io/badge/OpenAI-gpt--4o--mini--tts-green)](https://platform.openai.com/docs/guides/text-to-speech)

OpenAI TTS (`gpt-4o-mini-tts`) を使い、TOEIC Part 3 スタイルの **複数人英会話音声** を生成するCLIツールです。

## Features

- **2〜3名の会話** に対応（話者ごとに異なるボイス・スタイルを設定可能）
- JSON形式の会話スクリプト（transcript）から音声を一括生成
- 各発話の間に自然なポーズを挿入
- 個別WAV + 結合済みフルWAVを出力
- テキストのトランスクリプトも同時に生成

## Project Structure

```
toeic-tts/
├── main.py                   # 一括実行（transcript生成 → 音声合成）
├── generator/
│   ├── transcript.py         # 会話スクリプト生成（ChatCompletion）
│   └── tts.py                # 音声合成（TTS）
├── transcripts/              # 会話スクリプト (JSON)
│   └── sample_dialogue.json
├── output/                   # 生成された音声ファイル (gitignore)
├── pyproject.toml
├── .env                      # APIキー設定
└── README.md
```

## Prerequisites

- Python 3.8+
- [uv](https://docs.astral.sh/uv/) (パッケージマネージャ)
- OpenAI APIキー

## Setup

```bash
# リポジトリのクローン
git clone git@github.com:masanao-ohba/toeic-tts.git
cd toeic-tts

# 依存パッケージのインストール
uv sync

# APIキーの設定
echo 'API_KEY=sk-proj-your-key-here' > .env
```

## Usage

### 1. 一括実行（推奨）

`main.py` でtranscript生成から音声合成まで一発で実行できます。

```bash
# 2名の会話（デフォルト: 6ターン）
uv run python main.py --topic "hotel check-in"

# 3名の会話、8ターン
uv run python main.py --topic "project deadline" --speakers 3 --turns 8
```

### 2. 個別実行

各モジュールを単独で実行することも可能です。

#### 会話スクリプトの生成

```bash
uv run python -m generator.transcript --topic "hotel check-in"
uv run python -m generator.transcript --topic "project deadline" --speakers 3 --turns 8
```

生成されたJSONは `transcripts/` に保存されます。手動で作成・編集することも可能です。

```json
{
  "title": "Office Supplies and Delivery",
  "slug": "office_supplies_delivery",
  "speakers": {
    "W": {
      "voice": "marin",
      "speed": 0.96,
      "instructions": "Female office worker. Professional, calm, friendly."
    },
    "M": {
      "voice": "cedar",
      "speed": 0.98,
      "instructions": "Male office worker. Clear, neutral, professional."
    }
  },
  "lines": [
    {
      "speaker": "W",
      "text": "Hi, Daniel. Did the printer paper arrive this morning?",
      "pause_ms_after": 450
    },
    {
      "speaker": "M",
      "text": "Not yet. The supplier called and said the truck was delayed.",
      "pause_ms_after": 420
    }
  ]
}
```

#### 音声の生成

```bash
# 単一スクリプトの生成
uv run python -m generator.tts transcripts/sample_dialogue.json --outdir output

# 出力フォーマットやスピードのカスタマイズ
uv run python -m generator.tts transcripts/sample_dialogue.json \
  --outdir output \
  --speed 0.95 \
  --response-format wav
```

### 3. transcripts/ 配下を一括で音声生成する

```bash
for f in transcripts/*.json; do
  uv run python -m generator.tts "$f" --outdir "output/$(basename "$f" .json)"
done
```

## Dialogue JSON Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | Yes | 会話のタイトル |
| `slug` | string | No | 出力ファイル名のプレフィックス（デフォルト: `toeic_part3_dialogue`） |
| `speakers` | object | Yes | 話者の定義（キー: 話者ID） |
| `speakers.<id>.voice` | string | Yes | OpenAI TTSボイス名（`alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`, `coral`, `sage`, `ash`, `ballad`, `breeze`, `cedar`, `cove`, `ember`, `juniper`, `maple`, `marin`, `vale`） |
| `speakers.<id>.speed` | float | No | 話速（0.25〜4.0、デフォルト: 0.97） |
| `speakers.<id>.instructions` | string | No | 話し方の指示（`gpt-4o-mini-tts` で有効） |
| `lines` | array | Yes | 発話の配列 |
| `lines[].speaker` | string | Yes | 話者ID（`speakers` のキーと一致） |
| `lines[].text` | string | Yes | 発話テキスト |
| `lines[].pause_ms_after` | int | No | 発話後のポーズ（ms、デフォルト: 400） |
| `lines[].voice` | string | No | 行単位でのボイス上書き |
| `lines[].speed` | float | No | 行単位での話速上書き |
| `lines[].instructions` | string | No | 行単位での指示上書き |

## CLI Options

### main.py（一括実行）

```
usage: main.py [-h] --topic TOPIC [--speakers {2,3}] [--turns TURNS]
               [--chat-model CHAT_MODEL] [--tts-model TTS_MODEL]
               [--speed SPEED] [--response-format {wav,mp3,flac,aac,opus,pcm}]
               [--transcript-dir TRANSCRIPT_DIR] [--audio-dir AUDIO_DIR]

options:
  --topic TOPIC             会話トピック（必須）
  --speakers {2,3}          話者数 (default: 2)
  --turns TURNS             ターン数 (default: 6)
  --chat-model CHAT_MODEL   ChatCompletion モデル (default: gpt-4o-mini)
  --tts-model TTS_MODEL     TTS モデル (default: gpt-4o-mini-tts)
  --speed SPEED             話速 0.25-4.0 (default: 0.97)
  --response-format         音声フォーマット (default: wav)
  --transcript-dir          transcript出力先 (default: transcripts)
  --audio-dir               音声出力先 (default: output)
```

### generator.tts（音声生成のみ）

```
usage: python -m generator.tts [-h] [--outdir OUTDIR] [--model MODEL]
                               [--response-format {wav,mp3,flac,aac,opus,pcm}]
                               [--speed SPEED]
                               dialogue_json
```

### generator.transcript（スクリプト生成のみ）

```
usage: python -m generator.transcript [-h] --topic TOPIC [--speakers {2,3}]
                                      [--turns TURNS] [--outdir OUTDIR]
                                      [--model MODEL]
```

## Output

```
output/
├── 01_W.wav                          # 各発話の個別音声
├── 02_M.wav
├── ...
├── office_supplies_delivery_full.wav  # 結合済みフル音声
└── transcript.txt                    # テキストトランスクリプト
```

## License

[MIT](LICENSE)
