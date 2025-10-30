"""Trends API endpoints."""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any

from app.services.trend_service import TrendService


router = APIRouter()


@router.get("/youtube")
async def get_youtube_trends(
    category: str = "all",
    region: str = "KR",
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get YouTube trending videos.

    Args:
        category: Video category (all, music, gaming, entertainment, etc.)
        region: Region code (KR, US, JP, etc.)
        limit: Number of videos to return
    """
    service = TrendService()

    try:
        trends = await service.get_youtube_trends(
            category=category,
            region=region,
            limit=limit
        )
        return trends
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recommend")
async def get_trend_recommendations(
    genre: str = "general",
    target_audience: str = "all",
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Get story recommendations based on current trends.

    Args:
        genre: Story genre preference
        target_audience: Target audience (all, senior, youth, etc.)
        limit: Number of recommendations
    """
    service = TrendService()

    try:
        recommendations = await service.get_recommendations(
            genre=genre,
            target_audience=target_audience,
            limit=limit
        )
        return recommendations
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyze")
async def analyze_trend(query: str) -> Dict[str, Any]:
    """
    Analyze a specific trend or topic.

    Args:
        query: Topic or keyword to analyze
    """
    service = TrendService()

    try:
        analysis = await service.analyze_trend(query)
        return analysis
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
