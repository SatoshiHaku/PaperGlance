//
//  APIKeys.swift
//  PaperGlance
//
//  Created by Satoshi Haku on 2025/03/09.
//

import Foundation

struct APIKeys {
    static let mistralApiKey: String = {
        guard let key = Bundle.main.object(forInfoDictionaryKey: "MISTRALAI_API_KEY") as? String, !key.isEmpty else {
            fatalError("❌ MISTRALAI_API_KEY が設定されていません！")
        }
        return key
    }()

    static let openaiApiKey: String = {
        guard let key = Bundle.main.object(forInfoDictionaryKey: "OPENAI_API_KEY") as? String, !key.isEmpty else {
            fatalError("❌ OPENAI_API_KEY が設定されていません！")
        }
        return key
    }()
}
