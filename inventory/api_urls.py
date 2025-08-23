from django.urls import path
from . import api_views

urlpatterns = [
    path('car/<int:car_id>/fetch_market_price/', api_views.FetchMarketPriceView.as_view(), name='fetch_market_price'),
    path('portfolio/calculate_valuation/', api_views.CalculatePortfolioView.as_view(), name='calculate_portfolio_valuation'),
]
