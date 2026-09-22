# "history = model.fit(gen_samples('training'), steps_per_epoch=50, epochs=500, verbose=False, callbacks=[monitor])"
def pytest_collection_modifyitems(config, items):
    count = 0
    for item in items:
        cell = getattr(item, "cell", None)
        if cell is None:
            continue

        path = str(getattr(item, "fspath", ""))

        if not path.endswith(".ipynb"):
            continue

        if cell.get("cell_type") != "code":
            continue

        old, new = "epochs=500,", "epochs=1,"
        if cell.source.count(old) == 1:
            cell.source = cell.source.replace(old, new)
            count += 1

    assert count == 1
