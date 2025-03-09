//
//  MarkdownToPDFConverter.swift
//  PaperGlance
//
//  Created by Satoshi Haku on 2025/03/09.
//

import PDFKit
import UIKit

class MarkdownToPDFConverter {
    static func convertToPDF(markdown: String, outputURL: URL) {
        let pdfMetaData = [
            kCGPDFContextCreator: "MyPDFTranslatorApp",
            kCGPDFContextAuthor: "YourName"
        ]
        let format = UIGraphicsPDFRendererFormat()
        format.documentInfo = pdfMetaData as [String: Any]

        let pageWidth: CGFloat = 612
        let pageHeight: CGFloat = 792
        let renderer = UIGraphicsPDFRenderer(bounds: CGRect(x: 0, y: 0, width: pageWidth, height: pageHeight), format: format)

        let data = renderer.pdfData { context in
            context.beginPage()

            let textFont = UIFont.systemFont(ofSize: 14)
            let paragraphStyle = NSMutableParagraphStyle()
            paragraphStyle.alignment = .left

            let attributes: [NSAttributedString.Key: Any] = [
                .font: textFont,
                .paragraphStyle: paragraphStyle
            ]

            let attributedText = NSAttributedString(string: markdown, attributes: attributes)
            let textRect = CGRect(x: 20, y: 20, width: pageWidth - 40, height: pageHeight - 40)
            attributedText.draw(in: textRect)
        }

        do {
            try data.write(to: outputURL)
            print("✅ PDF successfully saved to: \(outputURL.path)")
        } catch {
            print("❌ Error saving PDF:", error.localizedDescription)
        }
    }
}

