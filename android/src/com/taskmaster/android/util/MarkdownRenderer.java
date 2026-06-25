package com.taskmaster.android.util;

public class MarkdownRenderer {
    private static final String STYLE =
        "body{font-family:-apple-system,sans-serif;font-size:15px;line-height:1.6;padding:12px;margin:0;color:#212121;}" +
        "h1,h2,h3{color:#1a1a1a;margin-top:16px;}" +
        "code{background:#f4f4f4;padding:2px 5px;border-radius:3px;font-size:13px;font-family:monospace;}" +
        "pre{background:#f4f4f4;padding:12px;border-radius:4px;overflow-x:auto;}" +
        "pre code{background:none;padding:0;}" +
        "blockquote{border-left:3px solid #ccc;margin:8px 0;padding-left:12px;color:#555;}" +
        "ul,ol{padding-left:24px;}" +
        "a{color:#1565C0;}" +
        "hr{border:none;border-top:1px solid #ddd;margin:16px 0;}";

    public static String toHtml(String md) {
        if (md == null || md.trim().isEmpty()) return "";
        String[] lines = md.split("\n");
        StringBuilder out = new StringBuilder();
        out.append("<!DOCTYPE html><html><head><meta charset='utf-8'>" +
                   "<meta name='viewport' content='width=device-width,initial-scale=1'>" +
                   "<style>").append(STYLE).append("</style></head><body>");

        boolean inCode = false;
        boolean inUl   = false;
        boolean inOl   = false;
        StringBuilder codeBlock = new StringBuilder();
        int olCount = 1;

        for (int li = 0; li < lines.length; li++) {
            String line = lines[li];

            // Fenced code block
            if (line.startsWith("```")) {
                if (inCode) {
                    out.append("<pre><code>").append(esc(codeBlock.toString())).append("</code></pre>\n");
                    codeBlock.setLength(0); inCode = false;
                } else { inCode = true; }
                continue;
            }
            if (inCode) { codeBlock.append(line).append("\n"); continue; }

            // Close lists
            if (inUl && !line.startsWith("- ") && !line.startsWith("* ")) { out.append("</ul>\n"); inUl = false; }
            if (inOl && !line.matches("^\\d+\\.\\s.*")) { out.append("</ol>\n"); inOl = false; olCount = 1; }

            if (line.startsWith("### "))      out.append("<h3>").append(inline(line.substring(4))).append("</h3>\n");
            else if (line.startsWith("## ")) out.append("<h2>").append(inline(line.substring(3))).append("</h2>\n");
            else if (line.startsWith("# "))  out.append("<h1>").append(inline(line.substring(2))).append("</h1>\n");
            else if (line.matches("^-{3,}$") || line.matches("^={3,}$")) out.append("<hr/>\n");
            else if (line.startsWith("- ") || line.startsWith("* ")) {
                if (!inUl) { out.append("<ul>\n"); inUl = true; }
                out.append("<li>").append(inline(line.substring(2))).append("</li>\n");
            } else if (line.matches("^\\d+\\.\\s.*")) {
                if (!inOl) { out.append("<ol>\n"); inOl = true; }
                out.append("<li>").append(inline(line.replaceFirst("^\\d+\\.\\s", ""))).append("</li>\n");
            } else if (line.startsWith("> ")) {
                out.append("<blockquote>").append(inline(line.substring(2))).append("</blockquote>\n");
            } else if (line.trim().isEmpty()) {
                out.append("<br/>\n");
            } else {
                out.append("<p>").append(inline(line)).append("</p>\n");
            }
        }
        if (inUl) out.append("</ul>\n");
        if (inOl) out.append("</ol>\n");
        if (inCode) out.append("<pre><code>").append(esc(codeBlock.toString())).append("</code></pre>\n");
        out.append("</body></html>");
        return out.toString();
    }

    private static String inline(String text) {
        text = esc(text);
        text = text.replaceAll("\\*\\*(.+?)\\*\\*", "<strong>$1</strong>");
        text = text.replaceAll("__(.+?)__",          "<strong>$1</strong>");
        text = text.replaceAll("\\*(.+?)\\*",        "<em>$1</em>");
        text = text.replaceAll("_(.+?)_",            "<em>$1</em>");
        text = text.replaceAll("~~(.+?)~~",          "<del>$1</del>");
        text = text.replaceAll("`(.+?)`",            "<code>$1</code>");
        text = text.replaceAll("\\[([^]]+)]\\(([^)]+)\\)", "<a href=\"$2\">$1</a>");
        return text;
    }

    private static String esc(String s) {
        return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;");
    }
}
