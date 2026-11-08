"""Meal logging (calories and macros) and intake versus Garmin's energy expenditure.

Meals come from the user, typically through Claude Desktop and the MCP server
(`garminizer mcp`), or from the dashboard. See docs/claude-desktop.md.
"""

from garminizer.nutrition.service import MealNotFoundError, NutritionError

__all__ = ["MealNotFoundError", "NutritionError"]
