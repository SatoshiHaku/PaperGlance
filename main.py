from dotenv import load_dotenv
import os
import re
from mistralai import Mistral
from mistralai.models import OCRResponse
from openai import OpenAI
import tiktoken  # OpenAIのトークンカウント用ライブラリ
from tqdm import tqdm  # 進捗バー用ライブラリ


# トークナイザーを取得
enc = tiktoken.encoding_for_model("gpt-4o-mini")


def ocr_pdf(api_key, file_name, data_dir):
    if not api_key:
        raise ValueError("MISTRAL_API_KEYが設定されていません")

    # Mistral APIクライアントの作成
    client = Mistral(api_key=api_key)


    pdf_path = f"{data_dir}/{file_name}"

    # PDFをMistralにアップロード
    uploaded_pdf = client.files.upload(
        file={
            "file_name": file_name,
            "content": open(pdf_path, "rb"),
        },
        purpose="ocr"
    )

    # アップロードしたPDFのサイン付きURLを取得
    signed_url = client.files.get_signed_url(file_id=uploaded_pdf.id)

    # OCR処理を実行
    ocr_response = client.ocr.process(
        model="mistral-ocr-latest",
        document={
            "type": "document_url",
            "document_url": signed_url.url,
        },
        include_image_base64=True
    )
    return ocr_response

def save_markdown(content, filename="output.md"):
    """マークダウンの内容を指定したファイルに保存する"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Markdown saved to {filename}")


def replace_images_in_markdown(markdown_str: str, images_dict: dict) -> str:
    for img_name, base64_str in images_dict.items():
        markdown_str = markdown_str.replace(f"![{img_name}]({img_name})", f"![{img_name}]({base64_str})")
    return markdown_str

def get_combined_markdown(ocr_response: OCRResponse) -> str:
  markdowns: list[str] = []
  for page in ocr_response.pages:
    image_data = {}
    for img in page.images:
      image_data[img.id] = img.image_base64
    markdowns.append(replace_images_in_markdown(page.markdown, image_data))
  return "\n\n".join(markdowns)

def split_title_and_reference(content):
    """最初の `#` をタイトル、`# References` 部分のみを参考文献として分離し、それ以降は本文として扱う"""
    lines = content.split("\n")

    title = None
    reference = None
    body_start = 0
    reference_start = None
    next_header_after_reference = None

    # 最初の `# ` をタイトルとする
    for i, line in enumerate(lines):
        if line.startswith("# "):  # 最初に見つかったタイトル
            title = line.strip()
            body_start = i + 1  # タイトルの次の行から本文開始
            break

    # `# References` 以降を参考文献として扱う
    for i, line in enumerate(lines):
        if re.match(r"^#{1,2} References", line, re.IGNORECASE):  # `# References` または `## References`
            reference_start = i
            break

    # `# References` が見つかった場合、その後のヘッダーを探す
    if reference_start is not None:
        for i in range(reference_start + 1, len(lines)):
            if re.match(r"^#{1,6} ", lines[i]):  # 次のヘッダー（`#`, `##`, `###` ...）
                next_header_after_reference = i
                break

    # 本文の取得
    if reference_start is not None:
        body = "\n".join(lines[body_start:reference_start]).strip()  # `# References` より前は本文
        reference = "\n".join(lines[reference_start:next_header_after_reference]).strip() if next_header_after_reference else "\n".join(lines[reference_start:]).strip()
        body += "\n\n" + "\n".join(lines[next_header_after_reference:]).strip() if next_header_after_reference else ""  # `# References` 以降の新しいヘッダーがあれば本文に追加
    else:
        body = "\n".join(lines[body_start:]).strip()  # 参考文献がない場合はすべて本文
        reference = None

    return title, body, reference


def split_by_headings(content, max_tokens=8000):
    """見出しごとにチャンクを分割し、トークン数を調整"""
    sections = re.split(r"(^# .+?$)", content, flags=re.MULTILINE)  # 見出しで分割
    chunks = []
    current_chunk = ""

    for i in range(len(sections)):
        section = sections[i].strip()
        if not section:
            continue

        section_tokens = len(enc.encode(section))

        # 最大トークン数を超えた場合、新しいチャンクを開始
        if len(enc.encode(current_chunk)) + section_tokens > max_tokens:
            chunks.append(current_chunk.strip())
            current_chunk = section  # 新しいチャンク開始
        else:
            current_chunk += "\n" + section  # 継続して追加

    if current_chunk:  # 最後のチャンクを追加
        chunks.append(current_chunk.strip())

    return chunks

def translate_gpt(ocr_response: OCRResponse, api_key_openai) -> str:
    """OCRのMarkdownテキストを見出しごとにチャンク化して翻訳し、画像を再配置する"""

    client = OpenAI(api_key=api_key_openai)
    markdowns = []

    print(f"📄 {len(ocr_response.pages)}ページの翻訳を開始します...")

    for page_idx, page in enumerate(tqdm(ocr_response.pages, desc="ページ処理中", unit="page")):
        print(f"\n📝 ページ {page_idx + 1} / {len(ocr_response.pages)} を翻訳中...")

        image_data = {img.id: img.image_base64 for img in page.images}  # 画像情報を辞書に格納

        # タイトル・本文・参考文献を分離
        title, body, reference = split_title_and_reference(page.markdown)

        # 本文を見出しごとにチャンク化
        chunks = split_by_headings(body, max_tokens=8000)

        translated_chunks = []

        print(f"🔄 見出し単位の翻訳（{len(chunks)} チャンク）...")

        # 各チャンクをGPTで翻訳（進捗バー表示）
        for chunk_idx, chunk in enumerate(tqdm(chunks, desc=f"ページ {page_idx + 1} 翻訳中", unit="chunk")):
            try:
                completion = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "内容の英語の文章をマークダウンの形式を崩さずに日本語に翻訳してください。"},
                        {"role": "user", "content": chunk},
                    ],
                )
                translated_chunks.append(completion.choices[0].message.content)
                print(f"✅ チャンク {chunk_idx + 1} / {len(chunks)} 翻訳完了")

            except Exception as e:
                print(f"⚠️ チャンク {chunk_idx + 1} の翻訳中にエラー発生: {e}")
                translated_chunks.append(chunk)  # エラー時は元のテキストを使用

        # 翻訳後の本文を再結合
        translated_body = "\n".join(translated_chunks)

        # タイトル・翻訳済み本文・参考文献を再構成
        final_markdown = ""
        if title:
            final_markdown += title + "\n\n"
        final_markdown += translated_body + "\n\n"
        if reference:
            final_markdown += reference

        # 画像を元の位置に戻す
        final_markdown = replace_images_in_markdown(final_markdown, image_data)

        markdowns.append(final_markdown)

    print("\n🎉 すべてのページの翻訳が完了しました！")
    return "\n\n".join(markdowns)



if __name__ == "__main__":


    load_dotenv()  # .envファイルを読み込む

    api_key_mistralai = os.getenv("MISTRALAI_API_KEY")
    api_key_openai = os.getenv("OPENAI_API_KEY")

    # ローカルPDFのパス
    file_name = r"AttentionIsAllYouNeed.pdf"
    data_dir = f'data'
    
    ocr_response = ocr_pdf(api_key_mistralai, file_name, data_dir)

    paper_raw_md = get_combined_markdown(ocr_response)

    save_markdown(paper_raw_md, filename="output/test.md")
    
    paper_translated_md = translate_gpt(ocr_response, api_key_openai)

    save_markdown(paper_translated_md, filename="output/test_translated.md")


    