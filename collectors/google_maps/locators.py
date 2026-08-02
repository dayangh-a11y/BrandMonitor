class GoogleMapsLocators:
    # Google Maps search input id changes often; name/role are more stable.
    SEARCH_INPUT_CANDIDATES = [
        "input#searchboxinput",
        'input[name="q"]',
        'input[role="combobox"]',
        'input[aria-label*="Search"]',
        'input[aria-label*="جستجو"]',
    ]
    SEARCH_BUTTON = "button#searchbox-searchbutton"
    RESULTS_FEED = 'div[role="feed"]'
    RESULT_CARD = 'div[role="feed"] a.hfpxzc'
    RESULT_CARD_FALLBACK = "a.hfpxzc"

    PLACE_TITLE = "h1"
    PLACE_RATING = 'div.F7nice span[aria-hidden="true"]'
    PLACE_REVIEW_COUNT = "div.F7nice"

    REVIEWS_TAB_CANDIDATES = [
        'button[role="tab"][aria-label*="Reviews"]',
        'button[role="tab"][aria-label*="نظرات"]',
        'button[role="tab"][aria-label*="مرور"]',
        'button[aria-label*="Reviews"]',
        'button[aria-label*="نظرات"]',
        'button[aria-label*="مرور"]',
        'button[jsaction*="pane.rating.moreReviews"]',
        'button[jsaction*="reviewChart.moreReviews"]',
        'button[jsaction*="review"]',
    ]

    REVIEW_CARD = "div.jftiEf"
    REVIEW_CARD_ALT = "[data-review-id]"
    REVIEW_AUTHOR = "div.d4r55"
    REVIEW_RATING = 'span[role="img"]'
    REVIEW_DATE = "span.rsqaWe"
    REVIEW_TEXT = "span.wiI7pd"
    REVIEW_MORE = "button.w8nwRe"
    REVIEW_OWNER_RESPONSE = "div.CDe7pd"
    REVIEW_OWNER_RESPONSE_DATE = "span.DZSIDd"
    PLACE_PHONE = 'button[data-item-id^="phone"]'
    PLACE_ADDRESS = 'button[data-item-id="address"]'

    CONSENT_BUTTONS = [
        'button:has-text("Accept all")',
        'button:has-text("I agree")',
        'button:has-text("Accept")',
        'button:has-text("Reject all")',
        'button:has-text("پذیرش همه")',
        'button:has-text("موافقم")',
    ]

    LIMITED_VIEW_MARKERS = [
        "limited view of Google Maps",
        "نمای محدودی از Google Maps",
        "You're seeing a limited view",
    ]
