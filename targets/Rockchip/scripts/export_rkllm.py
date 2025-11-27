#!/usr/bin/env python3
"""
RKLLM Export Script
Stand-alone Python script to convert HuggingFace models to RKLLM format.
Usage: python3 export_rkllm.py --model <path> --output <path> --quant <type> --target <platform>
"""

import sys
import argparse
import os
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="Export HF Model to RKLLM")
    parser.add_argument("--model", required=True, help="Path to HuggingFace model directory")
    parser.add_argument("--output", required=True, help="Output path for .rkllm file")
    parser.add_argument("--quant", default="w8a8", choices=["w8a8", "w4a16"], help="Quantization type")
    parser.add_argument("--target", default="rk3588", choices=["rk3588", "rk3576"], help="Target NPU Platform")
    return parser.parse_args()

def validate_paths(model_path, output_path):
    # Input Sanitization (Basic)
    if not os.path.exists(model_path):
        print(f"Error: Model path does not exist: {model_path}")
        sys.exit(1)
    
    # Ensure output dir exists
    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

def main():
    args = parse_args()
    validate_paths(args.model, args.output)
    
    print(f"--- RKLLM Exporter ---")
    print(f"Model:  {args.model}")
    print(f"Target: {args.target}")
    print(f"Quant:  {args.quant}")

    # Lazy Import to fail gracefully if SDK is missing
    try:
        from rkllm.api import RKLLM
    except ImportError:
        print("CRITICAL: 'rkllm' module not found.")
        print("Ensure you are running this inside the 'llm-framework/rockchip' container.")
        sys.exit(1)

    llm = RKLLM()

    # 1. Load
    print(f"Loading model...")
    ret = llm.load_huggingface(model=args.model)
    if ret != 0:
        print(f"❌ Load failed (Code {ret})")
        sys.exit(ret)

    # 2. Build
    print(f"Building model...")
    ret = llm.build(
        do_quantization=True,
        optimization_level=1,
        quantized_dtype=args.quant,
        target_platform=args.target,
        num_npu_core=3 
    )
    if ret != 0:
        print(f"❌ Build failed (Code {ret})")
        sys.exit(ret)

    # 3. Export
    print(f"Exporting to {args.output}...")
    ret = llm.export_rkllm(args.output)
    if ret != 0:
        print(f"❌ Export failed (Code {ret})")
        sys.exit(ret)

    print("✅ Conversion completed successfully.")

if __name__ == "__main__":
    main()
