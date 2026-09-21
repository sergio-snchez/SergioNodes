# coding: utf-8

"""
custom print and log functions 
"""

UPSTREAM = ("LivePortrait (utils)", "https://github.com/KwaiVGI/LivePortrait", "utils vendidos via NKD")

__all__ = ['rprint', 'rlog']

try:
    from rich.console import Console
    console = Console()
    rprint = console.print
    rlog = console.log
except:
    rprint = print
    rlog = print
