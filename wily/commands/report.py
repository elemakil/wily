"""
Report command.

The report command gives a table of metrics for a specified list of files.
Will compare the values between revisions and highlight changes in green/red.
"""
import tabulate

from pathlib import Path
from shutil import copytree
from string import Template

from wily import logger, format_date, format_revision, MAX_MESSAGE_WIDTH
from wily.config import DEFAULT_GRID_STYLE
from wily.operators import resolve_metric, MetricType
from wily.state import State


def report(
    config, path, metrics, n, include_message=False, format="console", output=None
):
    """
    Show information about the cache and runtime.

    :param config: The configuration
    :type  config: :class:`wily.config.WilyConfig`

    :param path: The path to the file
    :type  path: ``str``

    :param metrics: Name of the metric to report on
    :type  metrics: ``str``

    :param n: Number of items to list
    :type  n: ``int``

    :param include_message: Include revision messages
    :type  include_message: ``bool``

    :param format: Output format
    :type  format: ``str``

    :param output: Output path
    :type  output: ``str``
    """
    logger.debug("Running report command")
    logger.info(f"-----------History for {metrics}------------")

    data = []
    metric_metas = []

    for metric in metrics:
        operator, key = metric.split(".")
        metric = resolve_metric(metric)
        # Set the delta colors depending on the metric type
        if metric.measure == MetricType.AimHigh:
            good_color = 32
            bad_color = 31
        elif metric.measure == MetricType.AimLow:
            good_color = 31
            bad_color = 32
        elif metric.measure == MetricType.Informational:
            good_color = 33
            bad_color = 33
        metric_meta = {
            "key": key,
            "operator": operator,
            "good_color": good_color,
            "bad_color": bad_color,
            "title": metric.description,
            "type": metric.type,
        }
        metric_metas.append(metric_meta)

    state = State(config)
    for archiver in state.archivers:
        # We have to do it backwards to get the deltas between releases
        history = state.index[archiver].revisions[:n][::-1]
        last = {}
        for rev in history:
            vals = []
            for meta in metric_metas:
                try:
                    logger.debug(
                        f"Fetching metric {meta['key']} for {meta['operator']} in {path}"
                    )
                    val = rev.get(config, archiver, meta["operator"], path, meta["key"])

                    last_val = last.get(meta["key"], None)
                    # Measure the difference between this value and the last
                    if meta["type"] in (int, float):
                        if last_val:
                            delta = val - last_val
                        else:
                            delta = 0
                        last[meta["key"]] = val
                    else:
                        # TODO : Measure ranking increases/decreases for str types?
                        delta = 0

                    if delta == 0:
                        delta_col = delta
                    elif delta < 0:
                        delta_col = f"\u001b[{meta['good_color']}m{delta:n}\u001b[0m"
                    else:
                        delta_col = f"\u001b[{meta['bad_color']}m+{delta:n}\u001b[0m"

                    if meta["type"] in (int, float):
                        k = f"{val:n} ({delta_col})"
                    else:
                        k = f"{val}"
                except KeyError as e:
                    k = f"Not found {e}"
                vals.append(k)
            if include_message:
                data.append(
                    (
                        format_revision(rev.revision.key),
                        rev.revision.message[:MAX_MESSAGE_WIDTH],
                        rev.revision.author_name,
                        format_date(rev.revision.date),
                        *vals,
                    )
                )
            else:
                data.append(
                    (
                        format_revision(rev.revision.key),
                        rev.revision.author_name,
                        format_date(rev.revision.date),
                        *vals,
                    )
                )
    descriptions = [meta["title"] for meta in metric_metas]
    if include_message:
        headers = ("Revision", "Message", "Author", "Date", *descriptions)
    else:
        headers = ("Revision", "Author", "Date", *descriptions)

    if format == "html":
        report_path = Path.cwd()
        if output:
            output = Path(output)
            if output.suffix == ".html":
                report_path /= output.parents[0]
                report_output = report_path.joinpath(output.name)
            else:
                report_path /= output
                report_output = report_path.joinpath("index.html")
        else:
            report_path /= "wily_report"
            report_output = report_path.joinpath("index.html")

        report_path.mkdir(exist_ok=True, parents=True)
        report_template = Template(open("wily/templates/report_template.html").read())

        table_headers = "".join([f"<th>{header}</th>" for header in headers])
        table_content = ""
        for line in data[::-1]:
            table_content += "<tr>"
            for element in line:
                table_content += f"<td>{element}</td>"
            table_content += "</tr>"

        report_template = report_template.safe_substitute(
            headers=table_headers, content=table_content
        )

        with report_output.open("w") as output:
            output.write(report_template)

        try:
            copytree("wily/templates/css", str(report_path / "css"))
        except FileExistsError:
            pass

        logger.info(f"wily report was saved to {report_path}")
    else:
        print(
            # But it still makes more sense to show the newest at the top, so reverse again
            tabulate.tabulate(
                headers=headers, tabular_data=data[::-1], tablefmt=DEFAULT_GRID_STYLE
            )
        )
