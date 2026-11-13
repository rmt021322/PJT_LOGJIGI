from .search import excerpt


def output_posts(posts, keyword=''):
    return [dict(title=post['title'], url=post['url'],
                 content=excerpt(post.get('content', ''), keyword),
                 match_in=post.get('match_in', 'title')) for post in posts]
