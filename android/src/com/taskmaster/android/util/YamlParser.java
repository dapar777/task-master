package com.taskmaster.android.util;

import java.util.ArrayList;
import java.util.List;

public class YamlParser {
    public String id = "";
    public String title = "";
    public String status = "todo";
    public int priority = 5;
    public String category = "";
    public List<String> tags = new ArrayList<>();
    public String created = "";
    public String modified = "";
    public double order = 0.0;
    public boolean flag = false;
    public List<String> refs = new ArrayList<>();

    public static YamlParser parse(String yaml) {
        YamlParser r = new YamlParser();
        if (yaml == null) return r;
        String[] lines = yaml.split("\n");
        int i = 0;
        while (i < lines.length) {
            String line = lines[i];
            String t = line.trim();
            if (t.isEmpty() || t.startsWith("#")) { i++; continue; }
            int col = t.indexOf(':');
            if (col < 0) { i++; continue; }
            String key = t.substring(0, col).trim();
            String val = t.substring(col + 1).trim();
            switch (key) {
                case "_id":       r.id = val; break;
                case "_title":    r.title = unquote(val); break;
                case "_status":   r.status = val; break;
                case "_priority": try { r.priority = Integer.parseInt(val); } catch (Exception ignored) {} break;
                case "_category": r.category = unquote(val); break;
                case "_created":  r.created = val; break;
                case "_modified": r.modified = val; break;
                case "_order":    try { r.order = Double.parseDouble(val); } catch (Exception ignored) {} break;
                case "_flag":     r.flag = "true".equalsIgnoreCase(val); break;
                case "_tags":
                    if (val.startsWith("[")) { r.tags = parseInline(val); }
                    else if (val.isEmpty()) { i++; r.tags = readList(lines, i); i += r.tags.size(); continue; }
                    break;
                case "_refs":
                    if (val.isEmpty()) { i++; r.refs = readList(lines, i); i += r.refs.size(); continue; }
                    break;
            }
            i++;
        }
        return r;
    }

    private static List<String> readList(String[] lines, int start) {
        List<String> out = new ArrayList<>();
        for (int i = start; i < lines.length; i++) {
            String t = lines[i].trim();
            if (!t.startsWith("-")) break;
            String v = t.substring(1).trim();
            if (!v.contains(":")) out.add(unquote(v));
        }
        return out;
    }

    private static List<String> parseInline(String s) {
        List<String> out = new ArrayList<>();
        String inner = s.replaceAll("^\\[|]$", "");
        for (String item : inner.split(",")) {
            String v = item.trim();
            if (!v.isEmpty()) out.add(unquote(v));
        }
        return out;
    }

    private static String unquote(String s) {
        if (s.length() >= 2 &&
            ((s.charAt(0) == '\'' && s.charAt(s.length()-1) == '\'') ||
             (s.charAt(0) == '"'  && s.charAt(s.length()-1) == '"'))) {
            return s.substring(1, s.length() - 1);
        }
        return s;
    }

    public static String serialize(YamlParser m) {
        StringBuilder sb = new StringBuilder();
        sb.append("_id: ").append(m.id).append("\n");
        sb.append("_title: ").append(m.title).append("\n");
        sb.append("_status: ").append(m.status).append("\n");
        sb.append("_priority: ").append(m.priority).append("\n");
        sb.append("_category: ").append(m.category).append("\n");
        if (m.tags.isEmpty()) sb.append("_tags: []\n");
        else sb.append("_tags: [").append(join(m.tags)).append("]\n");
        sb.append("_created: ").append(m.created).append("\n");
        sb.append("_modified: ").append(m.modified).append("\n");
        sb.append("_order: ").append(m.order).append("\n");
        sb.append("_flag: ").append(m.flag).append("\n");
        if (m.refs.isEmpty()) sb.append("_refs: []\n");
        else { sb.append("_refs:\n"); for (String ref : m.refs) sb.append("  - ").append(ref).append("\n"); }
        return sb.toString();
    }

    private static String join(List<String> list) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < list.size(); i++) {
            if (i > 0) sb.append(", ");
            sb.append(list.get(i));
        }
        return sb.toString();
    }
}
