package com.taskmaster.android.util;

import com.taskmaster.android.model.TaskNode;

import java.io.*;
import java.text.SimpleDateFormat;
import java.util.*;

public class TaskRepository {
    private static final SimpleDateFormat FMT =
        new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.getDefault());

    public static List<TaskNode> loadWorkspace(File dir) {
        if (dir == null || !dir.isDirectory()) return new ArrayList<>();
        File[] files = dir.listFiles();
        if (files == null) return new ArrayList<>();
        List<TaskNode> result = new ArrayList<>();
        for (File f : files) {
            if (f.isDirectory()) {
                TaskNode n = readFolder(f, 0);
                if (n != null) result.add(n);
            }
        }
        Collections.sort(result, new Comparator<TaskNode>() {
            public int compare(TaskNode a, TaskNode b) { return Double.compare(a.order, b.order); }
        });
        return result;
    }

    private static TaskNode readFolder(File folder, int depth) {
        String name = folder.getName();
        File yamlFile = new File(folder, name + ".yaml");
        if (!yamlFile.exists()) return null;
        String yamlText = readFile(yamlFile);
        if (yamlText == null) return null;
        YamlParser meta = YamlParser.parse(yamlText);

        TaskNode node = new TaskNode();
        node.id       = meta.id;
        node.title    = meta.title;
        node.status   = meta.status;
        node.priority = meta.priority;
        node.category = meta.category;
        node.tags     = meta.tags;
        node.created  = meta.created;
        node.modified = meta.modified;
        node.order    = meta.order;
        node.flag     = meta.flag;
        node.depth    = depth;
        node.folderPath = folder.getAbsolutePath();

        File mdFile = new File(folder, name + ".md");
        if (mdFile.exists()) {
            String body = readFile(mdFile);
            node.body = body != null ? body : "";
        }

        File[] sub = folder.listFiles();
        if (sub != null) {
            for (File f : sub) {
                if (f.isDirectory()) {
                    TaskNode child = readFolder(f, depth + 1);
                    if (child != null) node.children.add(child);
                }
            }
            Collections.sort(node.children, new Comparator<TaskNode>() {
                public int compare(TaskNode a, TaskNode b) { return Double.compare(a.order, b.order); }
            });
        }
        return node;
    }

    public static void saveMeta(TaskNode task) {
        File folder = new File(task.folderPath);
        String name = folder.getName();
        YamlParser meta = new YamlParser();
        meta.id       = task.id;
        meta.title    = task.title;
        meta.status   = task.status;
        meta.priority = task.priority;
        meta.category = task.category;
        meta.tags     = task.tags;
        meta.created  = task.created;
        meta.modified = FMT.format(new Date());
        meta.order    = task.order;
        meta.flag     = task.flag;
        writeFile(new File(folder, name + ".yaml"), YamlParser.serialize(meta));
    }

    public static void saveBody(TaskNode task, String body) {
        File folder = new File(task.folderPath);
        String name = folder.getName();
        writeFile(new File(folder, name + ".md"), body);
    }

    public static TaskNode createTask(File parentDir, String title, String status,
                                       int priority, String category, List<String> tags) {
        String folderName = sanitize(title);
        File taskFolder = new File(parentDir, folderName);
        if (!taskFolder.mkdirs()) return null;

        YamlParser meta = new YamlParser();
        meta.id       = UUID.randomUUID().toString().replace("-","").substring(0,8);
        meta.title    = title;
        meta.status   = status;
        meta.priority = priority;
        meta.category = category;
        meta.tags     = tags;
        String now    = FMT.format(new Date());
        meta.created  = now;
        meta.modified = now;
        meta.order    = System.currentTimeMillis();
        meta.flag     = false;

        writeFile(new File(taskFolder, folderName + ".yaml"), YamlParser.serialize(meta));
        writeFile(new File(taskFolder, folderName + ".md"), "");

        TaskNode node = new TaskNode();
        node.id = meta.id; node.title = title; node.status = status;
        node.priority = priority; node.category = category;
        node.tags = new ArrayList<>(tags); node.created = now; node.modified = now;
        node.order = meta.order; node.flag = false; node.body = "";
        node.folderPath = taskFolder.getAbsolutePath();
        return node;
    }

    private static String sanitize(String title) {
        String s = title.toLowerCase().replaceAll("[^a-z0-9]+", "_").replaceAll("_+$","");
        return s.length() > 48 ? s.substring(0, 48) : (s.isEmpty() ? "task" : s);
    }

    public static String readFile(File f) {
        try {
            BufferedReader r = new BufferedReader(new InputStreamReader(new FileInputStream(f), "UTF-8"));
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = r.readLine()) != null) sb.append(line).append("\n");
            r.close();
            return sb.toString();
        } catch (Exception e) { return null; }
    }

    private static void writeFile(File f, String content) {
        try {
            PrintWriter w = new PrintWriter(new OutputStreamWriter(new FileOutputStream(f), "UTF-8"));
            w.print(content);
            w.close();
        } catch (Exception e) { e.printStackTrace(); }
    }
}
