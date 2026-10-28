

def test_listing_links_ignore_navigation_header_and_footer():
    from app.domain.content import extract_html, same_site_links
    html = (b"<html><body><nav><a href='/'>Home</a></nav><header><a href='/about'>About</a></header>"
            b"<main><a href='/news/a.html'>Story A</a> <a href='/news/b.html'>Story B</a></main>"
            b"<footer><a href='/terms'>Terms</a></footer></body></html>")
    ex = extract_html(html, "https://example.org/news/")
    links = same_site_links(ex.links, "https://example.org/news/", 10)
    assert [u for u, _ in links] == ["https://example.org/news/a.html", "https://example.org/news/b.html"]
