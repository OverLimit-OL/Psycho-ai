from google import genai
from google.genai import types, Client, errors
from pydantic import BaseModel, Field
from typing import List
from enum import Enum


MODEL_ID = "gemini-2.5-flash"

instructions = """
You are an AI assistant that performs non-medical emotional text analysis.

Your goal:

Identify emotional patterns.

Detect signs of stress, sadness, anxiety, or overwhelming feelings.

Highlight key words or phrases that may indicate distress.

Provide general well-being guidance, not medical advice.

"need_doctor" decision: Set it True only if there are serious physical symptoms (e.g., chest pain, fainting), intense negative thoughts, or severe sleep/eating disturbances.

In "doctor_recommendation": Briefly explain why a doctor is needed (e.g., "Due to chest pain and stress, it is recommended to consult a cardiologist"). If no doctor is needed, write a simple preventative piece of advice.

Avoid diagnosis, treatment suggestions, or clinical terms.

The response should be in Arabic language.
"""


class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class PsychoAnalysisResult(BaseModel):
    anxiety: int = Field(
        ...,
        ge=0,
        le=10,
        description="Anxiety level from 0 to 10"
    )
    stress: int = Field(
        ...,
        ge=0,
        le=10,
        description="Stress level from 0 to 10"
    )
    depression: int = Field(
        ...,
        ge=0,
        le=10,
        description="Depression level from 0 to 10"
    )
    trigger_words: List[str] = Field(
        default_factory=list,
        description="A list of words that indicate danger or negative feelings"
    )
    risk_level: RiskLevel = Field(
        ...,
        depression="Risk level classification (Low, Medium, High)"
    )
    advice: str = Field(
        ...,
        min_length=50,
        description="Non-medical advice directed to the user, min_length=50L & max_length=500L"
    )
    need_doctor: bool = Field(
        ...,
        description="Is a doctor's visit recommended based on the symptoms?"
    )
    doctor_recommendation: str = Field(
        ...,
        description="Explain why a doctor's visit is recommended (or general advice if not needed)"
    )
    actionable_tasks: List[str] = Field(
        ...,
        min_items=2, 
        max_items=4,
        default_factory=list,
        description="A short list (2-4 points) of very specific and actionable steps that the user can implement right now."
    )

class PsychoAnalyzer:
    def __init__(self, api_key: str):
        self.client = Client(api_key=api_key)

    def analyze(self, text: str) -> PsychoAnalysisResult:
        contents = types.Part.from_text(text=text)

        try:
            response_ai = self.client.models.generate_content(
                model=MODEL_ID,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=instructions,
                    response_mime_type="application/json",
                    response_schema=PsychoAnalysisResult,
                )
            )

            return PsychoAnalysisResult.model_validate_json(response_ai.text)

        except errors.APIError as e:
            raise RuntimeError(f"{e.code}: {e.message}")
