#!/usr/bin/env python3
"""fapiao CLI — extract fapiao data from PDFs or fill the Excel form.

Usage:
  python -m fapiao.cli extract [file.pdf ...]
  python -m fapiao.cli fill {1,2}
"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog='python -m fapiao.cli',
        description='Process Chinese VAT invoices (fapiaos).',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    extract_p = sub.add_parser('extract', help='Extract data from fapiao PDF(s) to fapiaos.csv')
    extract_p.add_argument('files', nargs='*', metavar='file.pdf',
                           help='PDF files to process (default: combines data/ then scans root)')

    fill_p = sub.add_parser('fill', help='Fill the Excel VAT form from fapiaos.csv')
    fill_p.add_argument('run', choices=['1', '2'],
                        help='1 = date/number/quantity, 2 = amounts and VAT')

    args = parser.parse_args()

    if args.command == 'extract':
        sys.argv = [sys.argv[0]] + args.files
        from fapiao.extract import main as extract_main
        extract_main()
    else:
        sys.argv = [sys.argv[0], args.run]
        from fapiao.fill import main as fill_main
        fill_main()


if __name__ == '__main__':
    main()
