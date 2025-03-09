//
//  PDFProcessor.swift
//  PaperGlance
//
//  Created by Satoshi Haku on 2025/03/09.
//

import Foundation

struct MistralOCRResponse: Codable {
    struct Page: Codable {
        let markdown: String
    }
    let pages: [Page]
}

class PDFProcessor {
    static func processPDF(fileURL: URL, completion: @escaping (String?) -> Void) {
        let apiKey = APIKeys.mistralApiKey  // xcconfig から取得した APIキーを使用
        let url = URL(string: "https://api.mistral.ai/files")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")

        let task = URLSession.shared.uploadTask(with: request, fromFile: fileURL) { data, response, error in
            if let error = error {
                print("❌ ネットワークエラー: \(error.localizedDescription)")
                DispatchQueue.main.async {
                    completion(nil)
                }
                return
            }

            guard let data = data else {
                print("❌ データなしのレスポンス")
                DispatchQueue.main.async {
                    completion(nil)
                }
                return
            }

            do {
                let ocrResponse = try JSONDecoder().decode(MistralOCRResponse.self, from: data)
                let markdown = ocrResponse.pages.map { $0.markdown }.joined(separator: "\n\n")
                DispatchQueue.main.async {
                    completion(markdown)
                }
            } catch {
                print("❌ JSONデコードエラー: \(error.localizedDescription)")
                DispatchQueue.main.async {
                    completion(nil)
                }
            }
        }
        task.resume()
    }
}
