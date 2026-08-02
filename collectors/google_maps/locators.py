class GoogleMapsLocators:
    SEARCH_INPUT = 'input#searchboxinput'
    SEARCH_BUTTON = 'button#searchbox-searchbutton'
    RESULTS_FEED = 'div[role="feed"]'
    RESULT_CARD = 'div[role="feed"] a.hfpxzc'
    RESULT_CARD_FALLBACK = 'a.hfpxzc'

    PLACE_TITLE = "h1"
    PLACE_RATING = 'div.F7nice span[aria-hidden="true"]'
    PLACE_REVIEW_COUNT = "div.F7nice"

    REVIEWS_TAB_CANDIDATES = [
        'button[role="tab"][aria-label*="Reviews"]',
        'button[role="tab"][aria-label*="نظرات"]',
        'button[aria-label*="Reviews"]',
        'button[aria-label*="نظرات"]',
        'button[jsaction*="pane.rating.moreReviews"]',
        'button[jsaction*="reviewChart.moreReviews"]',
    ]

    SORT_BUTTON_CANDIDATES = [
        'button[aria-label*="Sort"]',
        'button[aria-label*="مرتب"]',
        'button[data-value="Sort"]',
        'button.HQzyZ',
    ]

    REVIEW_CARD = "div.jftiEf"
    REVIEW_AUTHOR = "div.d4r55"
    REVIEW_RATING = 'span[role="img"]'
    REVIEW_DATE = "span.rsqaWe"
    REVIEW_TEXT = "span.wiI7pd"
    REVIEW_MORE = "button.w8nwRe"

    CONSENT_BUTTONS = [
        'button:has-text("Accept all")',
        'button:has-text("I agree")',
        'button:has-text("Accept")',
        'button:has-text("پذیرش همه")',
        'button:has-text("موافقم")',
    ]

    BACK_BUTTON_CANDIDATES = [
        'button[aria-label="Back"]',
        'button[aria-label="بازگشت"]',
        'button.VfPpkd-icon-LgbsSe',
    ]
