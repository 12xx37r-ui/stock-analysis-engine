name: on-demand-stock-analysis (GAS central KIS token)

run-name: on-demand-${{ inputs.stock_code }}-${{ inputs.request_id }}-${{ github.run_number }}

on:
  workflow_dispatch:
    inputs:
      stock_code:
        description: "6자리 종목코드"
        required: true
        type: string
      industry_code:
        description: "산업코드"
        required: true
        default: "auto"
        type: string
      request_id:
        description: "GAS 요청 추적 ID"
        required: false
        default: "manual"
        type: string

permissions:
  contents: write
  actions: read


concurrency:
  group: on-demand-stock-analysis
  cancel-in-progress: true


jobs:

  analyze:

    name: Analyze ${{ inputs.stock_code }}

    runs-on: ubuntu-latest

    timeout-minutes: 30


    env:

      DART_API_KEY: ${{ secrets.DART_API_KEY }}

      KIS_DISABLED: "1"

      STOCK_CODE: ${{ inputs.stock_code }}

      INDUSTRY_CODE: ${{ inputs.industry_code }}

      REQUEST_ID: ${{ inputs.request_id }}


    steps:


      - name: Checkout

        uses: actions/checkout@v6

        with:

          fetch-depth: 0



      - name: Validate stock code

        shell: bash

        run: |

          set -euo pipefail

          if [[ ! "$STOCK_CODE" =~ ^[0-9]{6}$ ]]; then

            echo "::error::Invalid stock code"

            exit 1

          fi



      - name: Setup Python

        uses: actions/setup-python@v7

        with:

          python-version: "3.11"

          cache: pip

          cache-dependency-path: requirements.txt



      # 추가된 부분
      - name: Install Python dependencies

        shell: bash

        run: |

          set -euo pipefail

          python -m pip install --upgrade pip

          python -m pip install -r requirements.txt


          python - <<'PY'

          import requests

          print("REQUESTS VERSION:", requests.__version__)

          PY



      - name: Confirm GAS central KIS mode

        shell: bash

        run: |

          echo "KIS_DISABLED=${KIS_DISABLED}"

          echo "GitHub does not issue KIS token"



      - name: Prepare output

        shell: bash

        run: |

          mkdir -p output

          rm -f "output/${STOCK_CODE}.json"



      - name: Run general company engine

        shell: bash

        run: |

          set +e


          echo "GENERAL COMPANY ENGINE"

          echo "REQUEST=${REQUEST_ID}"


          python main.py \
            --stock-code "$STOCK_CODE" \
            --industry-code "$INDUSTRY_CODE"


          STATUS=$?


          set -e


          if [[ "$STATUS" != "0" ]]; then

            echo "::warning::main.py exit ${STATUS}"

          fi



          python - <<'PY'

          import json

          import os

          from pathlib import Path


          code=os.environ["STOCK_CODE"]

          path=Path("output") / f"{code}.json"


          if not path.exists():

              raise SystemExit(
                f"OUTPUT MISSING {path}"
              )


          data=json.loads(
              path.read_text(
                encoding="utf-8"
              )
          )


          if not isinstance(data,dict):

              raise SystemExit(
                "JSON ROOT INVALID"
              )


          print("GENERAL COMPANY OUTPUT PASS")

          print("기업명:",data.get("기업명"))

          print("종목코드:",data.get("종목코드"))

          PY




      - name: Upload analysis handoff

        uses: actions/upload-artifact@v5

        with:

          name: on-demand-analysis-${{ github.run_id }}

          path: output/${{ inputs.stock_code }}.json

          retention-days: 1



  publish:


    name: Publish ${{ inputs.stock_code }}


    needs: analyze


    runs-on: ubuntu-latest


    timeout-minutes: 15


    env:

      STOCK_CODE: ${{ inputs.stock_code }}



    steps:



      - name: Checkout latest repository

        uses: actions/checkout@v6

        with:

          fetch-depth: 0



      - name: Setup Python

        uses: actions/setup-python@v7

        with:

          python-version: "3.11"



      - name: Install publish dependencies

        run: |

          python -m pip install --upgrade pip

          python -m pip install -r requirements.txt



      - name: Download analyzed stock

        uses: actions/download-artifact@v6

        with:

          name: on-demand-analysis-${{ github.run_id }}

          path: /tmp/on-demand-output




      - name: Publish general company result

        shell: bash

        run: |


          set -euo pipefail


          test -f "/tmp/on-demand-output/${STOCK_CODE}.json"



          git config user.name "github-actions[bot]"

          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"



          git fetch origin "$GITHUB_REF_NAME"

          git reset --hard "origin/$GITHUB_REF_NAME"



          mkdir -p data/latest/stocks



          cp \
          "/tmp/on-demand-output/${STOCK_CODE}.json" \
          "data/latest/stocks/${STOCK_CODE}.json"



          python publish_on_demand.py \
          --stock-file \
          "data/latest/stocks/${STOCK_CODE}.json" \
          --latest-root data/latest



          python validate_published_feed.py \
          --file \
          "data/latest/stocks/${STOCK_CODE}.json" \
          --stock-code "$STOCK_CODE"



          git add data/latest



          git commit \
          -m "feat: publish ${STOCK_CODE} general lookup [skip ci]" \
          || echo "nothing changed"



          git push origin HEAD:$GITHUB_REF_NAME



      # 추가된 GAS 반영 확인용
      - name: Verify public feed

        shell: bash

        run: |


          set -euo pipefail


          FILE="data/latest/stocks/${STOCK_CODE}.json"


          test -f "$FILE"



          python - <<'PY'

          import json

          import os

          from pathlib import Path


          code=os.environ["STOCK_CODE"]


          p=Path(
            "data/latest/stocks"
          ) / f"{code}.json"


          data=json.loads(
            p.read_text(
              encoding="utf-8"
            )
          )


          print("PUBLIC FEED OK")

          print("기업명:",data.get("기업명"))

          print("코드:",data.get("종목코드"))

          print("가치평가:",
                data.get("가치평가",{}).get("산출상태")
          )

          PY



      - name: Upload final result

        uses: actions/upload-artifact@v5

        with:

          name: on-demand-stock-${{ inputs.stock_code }}

          path:

            data/latest/stocks/${{ inputs.stock_code }}.json

          retention-days: 3
