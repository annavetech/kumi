# Ask for something in plain words

You don't need to know any specialist's name, or even the right technical term, to use kumi. Say what you want; `yui` asks what it needs to know and explains the plan before doing anything.

## What you type

```
/yui I want a button on my site that lets people sign up for updates by email
```

## What happens

**yui** reads the request. It's a real feature, but the request does not say which part of the app this touches or what "signs up" should actually do, so it asks first instead of guessing.

> A couple of quick questions before I start. Where does the signup form go: a page you already have, or a new one? And when someone signs up, should their email just be saved somewhere for now, or does it need to go into a mailing list tool you already use?

You answer: an existing page, and for now just save the email somewhere kumi can find it later.

**yui states the plan, in plain language, and confirms.**

> Here's what I'll do: the architect will design where the signup form and its data fit into your existing project, then the implementer for your stack will build the form and save the emails, then a reviewer will check it before you ship. Go ahead?

You say yes. `yui` dispatches the design step, then the build, then the review, exactly as it described, and relays each result in the same plain terms.

## The point

You did not need to know a single specialist's name, or use any technical vocabulary. `yui` filled the one real gap in your request with a plain question, stated the plan in words you already used, and only then started work.
