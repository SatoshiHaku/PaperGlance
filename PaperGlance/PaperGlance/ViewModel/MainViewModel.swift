//
//  MainViewModel.swift
//  PaperGlance
//
//  Created by Satoshi Haku on 2025/03/09.
//

import SwiftUI

class MainViewModel: ObservableObject {
    @Published var translatedMarkdown: String? = nil
    @Published var isProcessing = false

    func processPDF(fileURL: URL) {
        isProcessing = true
        
        PDFProcessor.processPDF(fileURL: fileURL) { markdown in
            DispatchQueue.main.async {
                guard let markdown = markdown else {
                    print("❌ OCR処理に失敗しました")
                    self.isProcessing = false
                    return
                }
                self.translateMarkdown(markdown: markdown)
            }
        }
    }
    
    private func translateMarkdown(markdown: String) {
        Translator.translateMarkdown(text: markdown) { translatedText in
            DispatchQueue.main.async {
                if let translatedText = translatedText {
                    self.translatedMarkdown = translatedText
                } else {
                    print("❌ 翻訳に失敗しました")
                    self.translatedMarkdown = "翻訳エラー"
                }
                self.isProcessing = false
            }
        }
    }
}
