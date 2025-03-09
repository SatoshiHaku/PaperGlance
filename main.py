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
    """最初の `#` をタイトル、`# References` 部分を参考文献、それ以降を本文として分離"""
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

    # `# References` の後の次のヘッダーを探す
    if reference_start is not None:
        for i in range(reference_start + 1, len(lines)):
            if re.match(r"^#{1,6} ", lines[i]):  # `#`, `##`, `###` などの次のヘッダー
                next_header_after_reference = i
                break

    # 本文の取得
    if reference_start is not None:
        body = "\n".join(lines[body_start:reference_start]).strip()  # `# References` より前の本文
        reference = "\n".join(lines[reference_start:next_header_after_reference]).strip() if next_header_after_reference else "\n".join(lines[reference_start:]).strip()
        remaining_body = "\n".join(lines[next_header_after_reference:]).strip() if next_header_after_reference else ""

        # 参考文献を `[1]`, `[2]` ごとに改行する
        if reference:
            reference = re.sub(r"\s*(\[\d+\])", r"\n\1", reference).strip()

    else:
        body = "\n".join(lines[body_start:]).strip()  # 参考文献がない場合はすべて本文
        reference = None
        remaining_body = ""

    return title, body, reference, remaining_body



def split_by_headings(content, max_tokens=8000):
    """見出しごとにチャンクを分割し、トークン数を調整（途中で文章が途切れないようにする）"""
    sections = re.split(r"(^# .+?$)", content, flags=re.MULTILINE)  # 見出しで分割
    chunks = []
    current_chunk = ""
    current_token_count = 0

    def count_tokens(text):
        return len(enc.encode(text))

    for i in range(len(sections)):
        section = sections[i].strip()
        if not section:
            continue

        section_tokens = count_tokens(section)

        # 追加しても max_tokens を超えない場合はそのまま追加
        if current_token_count + section_tokens <= max_tokens:
            current_chunk += "\n" + section if current_chunk else section
            current_token_count += section_tokens
        else:
            # 既に何かがあるなら、まず今のチャンクを確定
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
                current_token_count = 0

            # 現在のセクションが1つのチャンクに収まる場合はそのまま追加
            if section_tokens <= max_tokens:
                current_chunk = section
                current_token_count = section_tokens
            else:
                # セクションが長すぎる場合、段落単位でさらに分割
                paragraphs = section.split("\n")
                temp_chunk = ""
                temp_token_count = 0

                for paragraph in paragraphs:
                    paragraph = paragraph.strip()
                    if not paragraph:
                        continue
                    paragraph_tokens = count_tokens(paragraph)

                    # 追加してもオーバーしないならそのまま追加
                    if temp_token_count + paragraph_tokens <= max_tokens:
                        temp_chunk += "\n" + paragraph if temp_chunk else paragraph
                        temp_token_count += paragraph_tokens
                    else:
                        # 既に何かがあるなら、確定
                        if temp_chunk:
                            chunks.append(temp_chunk.strip())
                            temp_chunk = ""
                            temp_token_count = 0

                        # 今の段落が1つのチャンクに収まるなら新規チャンクにする
                        if paragraph_tokens <= max_tokens:
                            temp_chunk = paragraph
                            temp_token_count = paragraph_tokens
                        else:
                            # 1段落でも max_tokens を超えるなら、文章単位でさらに分割
                            sentences = re.split(r"(?<=[.!?])\s+", paragraph)  # 文単位で分割
                            sentence_chunk = ""
                            sentence_token_count = 0

                            for sentence in sentences:
                                sentence = sentence.strip()
                                if not sentence:
                                    continue
                                sentence_tokens = count_tokens(sentence)

                                if sentence_token_count + sentence_tokens <= max_tokens:
                                    sentence_chunk += " " + sentence if sentence_chunk else sentence
                                    sentence_token_count += sentence_tokens
                                else:
                                    if sentence_chunk:
                                        chunks.append(sentence_chunk.strip())
                                    sentence_chunk = sentence
                                    sentence_token_count = sentence_tokens

                            if sentence_chunk:
                                chunks.append(sentence_chunk.strip())

                if temp_chunk:
                    chunks.append(temp_chunk.strip())

    if current_chunk:  # 最後のチャンクを追加
        chunks.append(current_chunk.strip())

    return chunks


# def translate_gpt(ocr_response, api_key_openai):
#     """OCRのMarkdownテキストを一括で処理し、見出しごとにチャンク化して翻訳し、画像を再配置する"""

#     client = OpenAI(api_key=api_key_openai)

#     print(f"📄 {len(ocr_response.pages)}ページの翻訳を開始します...")

#     # 全ページのマークダウンを結合
#     combined_markdown = get_combined_markdown(ocr_response)

#     # タイトル・本文・参考文献・残りの本文を分離
#     title, body, reference, remaining_body = split_title_and_reference(combined_markdown)

#     # 本文と `# References` 以降の本文を見出し単位でチャンク化
#     body_chunks = split_by_headings(body, max_tokens=8000)
#     remaining_chunks = split_by_headings(remaining_body, max_tokens=8000)
#     chunks = body_chunks + remaining_chunks

#     translated_chunks = []

#     print(f"🔄 見出し単位の翻訳（{len(chunks)} チャンク）...")

#     # 各チャンクをGPTで翻訳
#     for chunk_idx, chunk in enumerate(tqdm(chunks, desc="翻訳中", unit="chunk")):
#         try:
#             completion = client.chat.completions.create(
#                 model="gpt-4o-mini",
#                 messages=[
#                     {"role": "system", "content": "内容の英語の文章をマークダウンの形式を崩さずに日本語に翻訳してください。"},
#                     {"role": "user", "content": chunk},
#                 ],
#             )
#             translated_chunks.append(completion.choices[0].message.content)
#             print(f"✅ チャンク {chunk_idx + 1} / {len(chunks)} 翻訳完了")

#         except Exception as e:
#             print(f"⚠️ チャンク {chunk_idx + 1} の翻訳中にエラー発生: {e}")
#             translated_chunks.append(chunk)  # エラー時は元のテキストを使用

#     # 翻訳後の本文を再結合
#     translated_body = "\n".join(translated_chunks[:len(body_chunks)])
#     translated_remaining_body = "\n".join(translated_chunks[len(body_chunks):])

#     # タイトル・翻訳済み本文・参考文献を再構成
#     final_markdown = ""
#     if title:
#         final_markdown += title + "\n\n"
#     final_markdown += translated_body + "\n\n"
#     if reference:
#         final_markdown += reference + "\n\n"
#     final_markdown += translated_remaining_body

#     # 画像データを元の位置に戻す
#     image_data = {img.id: img.image_base64 for page in ocr_response.pages for img in page.images}
#     final_markdown = replace_images_in_markdown(final_markdown, image_data)

#     print("\n🎉 翻訳完了！")
#     return final_markdown


def extract_and_replace_images(markdown):
    """Markdown から画像部分を抽出し、プレースホルダーに置き換える"""
    image_pattern = r"(!\[[^\]]*\]\([^\)]+\))"  # `![alt](image_url)`
    images = re.findall(image_pattern, markdown)  # 画像部分を抽出
    placeholders = [f"{{IMAGE_{i}}}" for i in range(len(images))] 
    
    # 画像をプレースホルダーに置換
    modified_markdown = markdown
    for img, placeholder in zip(images, placeholders):
        modified_markdown = modified_markdown.replace(img, placeholder, 1)

    return modified_markdown, images, placeholders

def restore_images(markdown, images, placeholders):
    """プレースホルダーを元の画像に戻す"""
    for img, placeholder in zip(images, placeholders):
        markdown = markdown.replace(placeholder, img, 1)
    return markdown

def translate_gpt(ocr_response, api_key_openai):
    """OCRのMarkdownテキストを一括で処理し、画像を翻訳せずにそのまま維持する"""

    client = OpenAI(api_key=api_key_openai)

    print(f"📄 {len(ocr_response.pages)}ページの翻訳を開始します...")

    # 全ページのマークダウンを結合
    combined_markdown = get_combined_markdown(ocr_response)

    # 画像をプレースホルダーに置き換え
    combined_markdown, images, placeholders = extract_and_replace_images(combined_markdown)

    # タイトル・本文・参考文献・残りの本文を分離
    title, body, reference, remaining_body = split_title_and_reference(combined_markdown)

    # 本文と `# References` 以降の本文を見出し単位でチャンク化
    body_chunks = split_by_headings(body, max_tokens=8000)
    remaining_chunks = split_by_headings(remaining_body, max_tokens=8000)
    chunks = body_chunks + remaining_chunks

    translated_chunks = []

    print(f"🔄 見出し単位の翻訳（{len(chunks)} チャンク）...")

    # 各チャンクをGPTで翻訳
    for chunk_idx, chunk in enumerate(tqdm(chunks, desc="翻訳中", unit="chunk")):
        try:
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "内容の英語の文章をマークダウンの形式を崩さずに日本語に翻訳してください。ただし、{IMAGE_X} のようなプレースホルダーはそのまま維持してください。"},
                    {"role": "user", "content": chunk},
                ],
            )
            translated_chunks.append(completion.choices[0].message.content)
            print(f"✅ チャンク {chunk_idx + 1} / {len(chunks)} 翻訳完了")

        except Exception as e:
            print(f"⚠️ チャンク {chunk_idx + 1} の翻訳中にエラー発生: {e}")
            translated_chunks.append(chunk)  # エラー時は元のテキストを使用

    # 翻訳後の本文を再結合
    translated_body = "\n".join(translated_chunks[:len(body_chunks)])
    translated_remaining_body = "\n".join(translated_chunks[len(body_chunks):])

    # タイトル・翻訳済み本文・参考文献を再構成
    final_markdown = ""
    if title:
        final_markdown += title + "\n\n"
    final_markdown += translated_body + "\n\n"
    if reference:
        final_markdown += reference + "\n\n"
    final_markdown += translated_remaining_body

    # 画像データを元の位置に戻す
    final_markdown = restore_images(final_markdown, images, placeholders)

    print("\n🎉 翻訳完了！")
    return final_markdown

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


    