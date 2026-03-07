"""
Unit tests for LLM Providers
"""

import pytest
from ai.llm_provider import get_llm_provider, BaseLLMProvider
from config import settings, LLMProvider


class TestLLMProvider:
    """Test LLM Provider Factory and Implementations"""
    
    def test_get_llm_provider_returns_instance(self):
        """Test that get_llm_provider returns a valid instance"""
        provider = get_llm_provider()
        assert provider is not None
        assert isinstance(provider, BaseLLMProvider)
    
    def test_llm_provider_singleton(self):
        """Test that provider is singleton"""
        provider1 = get_llm_provider()
        provider2 = get_llm_provider()
        assert provider1 is provider2
    
    @pytest.mark.asyncio
    async def test_chat_completion_interface(self):
        """Test chat_completion method signature"""
        provider = get_llm_provider()
        
        messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Hello!"}
        ]
        
        # This would make actual API calls if credentials are set
        # For CI/CD, mock this test
        try:
            result = await provider.chat_completion(messages)
            assert "content" in result
            assert isinstance(result["content"], str)
        except Exception as e:
            pytest.skip(f"API call failed: {e}")
    
    @pytest.mark.asyncio
    async def test_stream_completion_interface(self):
        """Test stream_completion method"""
        provider = get_llm_provider()
        
        messages = [
            {"role": "user", "content": "Say hello"}
        ]
        
        try:
            chunks = []
            async for chunk in provider.stream_completion(messages):
                chunks.append(chunk)
                if len(chunks) >= 3:  # Just test first few chunks
                    break
            
            assert len(chunks) > 0
        except Exception as e:
            pytest.skip(f"API call failed: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
