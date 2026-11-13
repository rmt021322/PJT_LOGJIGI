def rank_posts(posts, keyword, limit=3):
    terms = keyword.casefold().split()
    def score(post):
        title = post['title'].casefold()
        content = post.get('content', '').casefold()
        return (post.get('match_in', 'title') == 'title',
                sum(term in title for term in terms),
                sum(term in content for term in terms),
                -post.get('source_order', 0))
    return sorted(posts, key=score, reverse=True)[:limit]
