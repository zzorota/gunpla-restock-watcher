# ガンプラ再販ウォッチャー

Amazon.co.jp / ヨドバシ.com / ホビーサーチ(1999.co.jp) / プレミアムバンダイ の商品ページを
定期的にチェックし、「在庫なし → 在庫あり」に変わったタイミングでDiscordに通知します。
GitHub Actions 上で10分おきに自動実行され、費用はかかりません（リポジトリを公開設定にした場合）。

## 1. Discord Webhookを用意する

1. 通知を受け取りたいDiscordサーバーでチャンネルを右クリック →「連携サービス」
2. 「ウェブフックを作成」→ 名前を適当に設定 →「ウェブフックURLをコピー」
   （このURLは他人に見せないでください。知っていれば誰でもそのチャンネルに投稿できます）

## 2. GitHubリポジトリを作る

1. GitHubで新しいリポジトリを作成（**Public（公開）推奨** — Publicなら Actions の実行時間が無料枠無制限）
2. このフォルダの中身をpushする

```powershell
git init
git add .
git commit -m "init: gunpla restock watcher"
git branch -M main
git remote add origin https://github.com/<あなたのアカウント>/<リポジトリ名>.git
git push -u origin main
```

## 3. Webhook URLをSecretに登録する

1. リポジトリの `Settings` → `Secrets and variables` → `Actions` → `New repository secret`
2. Name: `DISCORD_WEBHOOK_URL`
3. Value: 手順1でコピーしたWebhook URL

## 4. 監視したい商品を登録する

`products.yaml` を編集して、監視したい商品ページのURLを追加してください。

```yaml
products:
  - name: "HG 001 ガンダム"
    url: "https://www.amazon.co.jp/dp/XXXXXXXXXX"

  - name: "MG フリーダムガンダム Ver.2.0"
    url: "https://www.1999.co.jp/itembig/XXXXXXXX"
```

サンプルの2件は `disabled: true` になっているので、実際の商品に書き換えたら
その行を削除するか、新しく行を追加してください。

編集したら `git add products.yaml && git commit -m "add products" && git push` で反映します。

## 5. 動作確認

1. GitHubリポジトリの `Actions` タブ → `Gunpla Restock Watch` → `Run workflow` で手動実行
2. 実行ログでエラーが出ていないか確認
3. 以降は10分おきに自動実行されます（`.github/workflows/watch.yml` の cron を変更すれば間隔を調整可能）

## 注意点

- **Amazon.co.jpはボット対策が強く、GitHub ActionsのIPからだとCAPTCHAでブロックされることがあります。**
  ブロックされると一度だけ警告がDiscordに届きます。頻発する場合はAmazonの監視を諦めるか、
  自分のPCから `python -m watcher.main` を実行する運用に切り替えてください。
- 各サイトのHTML構造が変わると判定が効かなくなることがあります。その場合は
  `watcher/checkers.py` の該当サイトの関数（キーワードやセレクタ）を調整してください。
- 個人の趣味利用・常識的な頻度（10分間隔程度）での利用を想定しています。
  各サイトの利用規約の範囲内でご利用ください。
- 初回チェック時点で在庫ありの商品については通知しません（2回目以降、状態が変化した時のみ通知）。

## ローカルで試す場合

```powershell
pip install -r requirements.txt
$env:DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/xxxx"
python -m watcher.main
```
