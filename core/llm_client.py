from __future__ import annotations

try:
    from openai import OpenAI
except ImportError as exc:
    raise RuntimeError("Missing dependency: openai. Run `pip install openai`.") from exc


class AIClient:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate_annotation(self, target_code: str, repomap_context: str, language: str) -> str | None:
        numbered_code = "\n".join(
            f"{index + 1:04d} | {line}" for index, line in enumerate(target_code.splitlines())
        )

        system_prompt = (
            "You are a senior code analysis assistant. "
            "Use the repository map and the numbered target source to write a concise, factual analysis. "
            "Identify important cross-file relationships and call out defects or structural risks directly. "
            "When you describe specific logic, reference the physical line ranges from the numbered code. "
            "Return Markdown."
        )
        user_prompt = (
            f"### Repository Context ###\n{repomap_context}\n\n"
            f"### Target Source ({language}) ###\n{numbered_code}"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
            )
        except Exception as exc:
            return f"[API Error] Unable to get response: {exc}"

        return response.choices[0].message.content
