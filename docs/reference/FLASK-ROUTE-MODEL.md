# Flask route introspection

sharpit's pytest adapter can inspect Flask routes from Flask 2.3.3 onward. Flask stays in the `test` extra; it is not a
runtime dependency. Route discovery uses registered `url_map` rules and does not execute view functions. Blueprint
rules appear as Flask registers them, including static routes and distinct registrations of the same view.

Werkzeug paths such as `/items/<int:item_id>` appear as `/items/{item_id}`. The adapter reports effective rule methods,
including automatically added `HEAD` and `OPTIONS`, and preserves the rule's slash spelling.

The route model has no fields for `strict_slashes`, subdomain or host constraints, converter semantics, blueprint
provenance, declared-versus-automatic methods, response metadata, or produced and consumed media types. These facts are
not inferred; host is `null`, and unavailable response and media metadata are `null`. A malformed or unreadable URL map
produces no routes, allowing the pytest advisor to report `UNKNOWN` when route presence is required.

Flask route introspection does not mount the sharpit console in Flask applications.
