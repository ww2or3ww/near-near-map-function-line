# near-near-map-function-line


## ライブラリのインストール
$ pip install -r requirements.txt -t source


## パッケージング&デプロイ コマンド

```
$ find . | grep -E "(__pycache__|\.pyc|\.pyo$)" | xargs rm -rf
$ cd source
$ zip -r ../lambda-package.zip *
$ aws lambda update-function-code --function-name near-near-map-line --zip-file fileb://../lambda-package.zip
```
