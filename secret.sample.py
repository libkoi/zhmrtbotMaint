# You need to register an OAuth consumer in Special:OAuthConsumerRegistration
# - Select "Propose new OAuth 1.0a consumer"
# - Fill the form.
#     - "OAuth 'callback' URL" should be something like:
#        http://localhost:5000/oauth-callback, please adjust hostname and port
#        according to your own settings
#     - Please do not select "Allow consumer to specify..." checkbox
#     - Grants should be "User identity verification only, no ability to ..."
#     - "Applicable project" should be "*" ("All project on this site")
# - You will receive two tokens: "consumer token" (publicly available) and
#   "secret token" (like your program's password). Paste them to file "secret.py"
#   under variables defined in this sample file.

customer_token = ""
secret_token = ""
