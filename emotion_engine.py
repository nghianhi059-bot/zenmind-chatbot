from underthesea import sentiment

class EmotionEngine:
    @staticmethod
    def analyze_text(text: str):
        # Hàm sentiment của underthesea trả về 'positive', 'negative' hoặc 'neutral'
        result = sentiment(text)

        # Logic tùy chỉnh cho tư vấn tâm lý
        if result == 'negative':
            label = "Buồn/Lo âu"
            score = 0.1
        elif result == 'positive':
            label = "Tích cực/Vui vẻ"
            score = 0.9
        else:
            label = "Trung tính"
            score = 0.5

        return {"label": label, "score": score, "original_sentiment": result}
