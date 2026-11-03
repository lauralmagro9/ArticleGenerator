from unittest.mock import MagicMock, patch
import config
import pytest
from services.wordpress_service import WordPress


class TestWordPress:
    def test_get_published_posts(self):
        wp = WordPress(config.WORDPRESS_URL, config.WORDPRESS_USER, config.WORDPRESS_PASSWORD)
        posts = wp.get_published_posts()
        assert posts

    def test_get_or_create_category(self, app):
        category = "Boletus"
        WP_CLASS = WordPress()
        category_id = WP_CLASS.get_or_create_category(category)
        assert isinstance(category_id, list)
        assert isinstance(category_id[0], int)

    @pytest.mark.parametrize(
        "title, content, metadescription, category_id", 
        [
            ('Test Title', 'test content', 'test meta', 1),
        ]
    )
    def test_post_draft_to_wordpress(self, title,
        content,
        metadescription,
        category_id):
        url=config.WORDPRESS_URL
        user=config.WORDPRESS_USER
        password=config.WORDPRESS_PASSWORD
        wp = WordPress(config.WORDPRESS_URL, config.WORDPRESS_USER, config.WORDPRESS_PASSWORD)
        post_id, post_link = wp.post_draft_to_wordpress(title, content, metadescription, category_id)
        assert post_id
        assert post_link

    def test_upload_image(self, app, image_file):
        WP_CLASS = WordPress()
        result = WP_CLASS.upload_image(image_file, "desc")
        assert isinstance(result, int)

    #@pytest.mark.parametrize("status_code,expected_url", [(201, "https://example.com/post"), (400, None)])
    #def test_upload_post_creates_draft(self, app, status_code, expected_url):
    #    with patch("ArticleGenerator.services.wordpress_services.requests.post") as mock_post:
    #        mock_post.return_value.status_code = status_code
    #        mock_post.return_value.json.return_value = {"guid": {"rendered": "https://example.com/post"}}
#
    #        WP_CLASS = WordPress()
    #        result = WP_CLASS.upload_post("<h1>Title</h1><p>Body</p>", "image.jpg", 1)
    #        
    #        assert result == expected_url
           

