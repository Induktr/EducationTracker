import google.generativeai as genai
from typing import Dict, List, Tuple
import json
from config import GEMINI_API_KEY, EXPERIENCE_LEVELS
from logger import logger

class GeminiAnalyzer:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("Gemini API key not found in environment variables")
        
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-pro')

    def analyze_job_description(self, job_description: str) -> Dict[str, any]:
        """
        Analyze job description using Gemini AI
        Returns dict with experience level and other insights
        """
        try:
            prompt = f"""
            Analyze this job description and provide the following information in JSON format:
            1. Experience level (junior/middle)
            2. Key technical skills required
            3. Main responsibilities
            4. Nice-to-have skills
            
            Job Description:
            {job_description}
            """

            response = self.model.generate_content(prompt)
            analysis = json.loads(response.text)
            
            logger.log_job_processing(
                "gemini_analysis",
                "success",
                {"length": len(job_description)}
            )
            
            return analysis

        except Exception as e:
            logger.log_error(
                "gemini_analysis_error",
                str(e),
                {"description_length": len(job_description)}
            )
            raise

    def determine_experience_level(self, job_description: str) -> str:
        """
        Determine if a job is junior or middle level
        Returns: "junior" or "middle"
        """
        try:
            # Count occurrences of level-specific keywords
            desc_lower = job_description.lower()
            
            junior_score = sum(1 for keyword in EXPERIENCE_LEVELS["junior"] 
                             if keyword in desc_lower)
            middle_score = sum(1 for keyword in EXPERIENCE_LEVELS["middle"] 
                             if keyword in desc_lower)
            
            # Use Gemini for additional context
            prompt = f"""
            Based on this job description, determine if this is a junior or middle level position.
            Return only "junior" or "middle".
            
            Description: {job_description}
            """
            
            response = self.model.generate_content(prompt)
            ai_level = response.text.strip().lower()
            
            # Combine keyword matching with AI analysis
            if junior_score > middle_score or ai_level == "junior":
                return "junior"
            return "middle"

        except Exception as e:
            logger.log_error(
                "experience_level_error",
                str(e),
                {"description_length": len(job_description)}
            )
            raise

    def extract_key_skills(self, job_description: str) -> List[str]:
        """Extract key technical skills from job description"""
        try:
            prompt = f"""
            Extract the key technical skills from this job description.
            Return them as a comma-separated list.
            
            Description: {job_description}
            """
            
            response = self.model.generate_content(prompt)
            skills = [skill.strip() for skill in response.text.split(",")]
            
            return skills

        except Exception as e:
            logger.log_error(
                "skills_extraction_error",
                str(e),
                {"description_length": len(job_description)}
            )
            raise
