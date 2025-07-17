#!/usr/bin/env python3
"""
Test the improved attempt_multiple_times function with telescoping delays
"""

import sys
import os
from time import time
import unittest
from unittest.mock import Mock, patch

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(os.path.dirname(script_dir), 'utils'))

from rocotostat import attempt_multiple_times


class TestAttemptMultipleTimes(unittest.TestCase):
    
    def test_successful_first_attempt(self):
        """Test function that succeeds on first attempt"""
        mock_func = Mock(return_value="success")
        
        result = attempt_multiple_times(mock_func, 3, 1)
        
        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 1)
    
    def test_telescoping_delay(self):
        """Test telescoping delay functionality"""
        # Create a function that fails twice then succeeds
        mock_func = Mock(side_effect=[ValueError("fail1"), ValueError("fail2"), "success"])
        
        start_time = time()
        result = attempt_multiple_times(mock_func, 3, 1, ValueError, use_telescoping_delay=True)
        end_time = time()
        
        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 3)
        # Should take at least 1 + 2 = 3 seconds with telescoping delay
        self.assertGreaterEqual(end_time - start_time, 3.0)
    
    def test_fixed_delay(self):
        """Test fixed delay functionality"""
        # Create a function that fails twice then succeeds
        mock_func = Mock(side_effect=[ValueError("fail1"), ValueError("fail2"), "success"])
        
        start_time = time()
        result = attempt_multiple_times(mock_func, 3, 1, ValueError, use_telescoping_delay=False)
        end_time = time()
        
        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 3)
        # Should take at least 1 + 1 = 2 seconds with fixed delay
        self.assertGreaterEqual(end_time - start_time, 2.0)
        self.assertLess(end_time - start_time, 3.0)  # Should be less than telescoping delay
    
    def test_all_attempts_fail(self):
        """Test when all attempts fail"""
        mock_func = Mock(side_effect=ValueError("always fails"))
        
        with self.assertRaises(ValueError):
            attempt_multiple_times(mock_func, 3, 0.1, ValueError)
        
        self.assertEqual(mock_func.call_count, 3)
    
    def test_no_delay(self):
        """Test with no delay between attempts"""
        mock_func = Mock(side_effect=[ValueError("fail1"), ValueError("fail2"), "success"])
        
        start_time = time()
        result = attempt_multiple_times(mock_func, 3, 0, ValueError)
        end_time = time()
        
        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 3)
        # Should complete very quickly with no delay
        self.assertLess(end_time - start_time, 0.1)


if __name__ == '__main__':
    unittest.main()