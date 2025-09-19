from django.urls import path
from . import api_views

urlpatterns = [
    path('car/<int:car_id>/fetch_market_price/', api_views.FetchMarketPriceView.as_view(), name='fetch_market_price'),
    path('portfolio/calculate_valuation/', api_views.CalculatePortfolioView.as_view(), name='calculate_portfolio_valuation'),
    # Market price management
    path('market_price/<int:price_id>/', api_views.DeleteMarketPriceView.as_view(), name='delete_market_price'),
    path('car/<int:car_id>/market_price/', api_views.AddManualMarketPriceView.as_view(), name='add_manual_market_price'),
    # Market fetch credits
    path('market_credits/status/', api_views.MarketCreditStatusView.as_view(), name='market_credit_status'),
]
