//
//  Translator.swift
//  PaperGlance
//
//  Created by Satoshi Haku on 2025/03/09.
//

import Foundation

struct OpenAIResponse: Codable {
    struct Choice: Codable {
        struct Message: Codable {
            let content: String
        }
        let message: Message
    }
    let choices: [Choice]
}
import Foundation

class Translator {
    static func translateMarkdown(text: String, completion: @escaping (String?) -> Void) {
        let apiKey = APIKeys.openaiApiKey  // xcconfig から取得した APIキーを使用
        let url = URL(string: "https://api.openai.com/v1/chat/completions")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let requestBody: [String: Any] = [
            "model": "gpt-4o",
            "messages": [
                ["role": "system", "content": "マークダウンのフォーマットを崩さずに英語を日本語に翻訳してください。"],
                ["role": "user", "content": text]
            ],
            "max_tokens": 8000
        ]

        do {
            let jsonData = try JSONSerialization.data(withJSONObject: requestBody)
            request.httpBody = jsonData
        } catch {
            print("❌ JSONエンコードエラー: \(error.localizedDescription)")
            completion(nil)
            return
        }

        let task = URLSession.shared.dataTask(with: request) { data, response, error in
            guard let data = data, error == nil else {
                print("❌ ネットワークエラー: \(error?.localizedDescription ?? "不明なエラー")")
                completion(nil)
                return
            }

            do {
                let response = try JSONDecoder().decode(OpenAIResponse.self, from: data)
                let translatedText = response.choices.first?.message.content
                completion(translatedText)
            } catch {
                print("❌ JSONデコードエラー: \(error.localizedDescription)")
                completion(nil)
            }
        }
        task.resume()
    }
}
