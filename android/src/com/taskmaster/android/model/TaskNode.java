package com.taskmaster.android.model;

import java.util.ArrayList;
import java.util.List;

public class TaskNode {
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
    public String body = "";
    public String folderPath = "";
    public List<TaskNode> children = new ArrayList<>();
    public int depth = 0;

    public boolean isDone() { return "done".equals(status); }

    public String statusLabel() {
        switch (status) {
            case "in_progress": return "Probíhá";
            case "blocked":     return "Blokováno";
            case "done":        return "Hotovo";
            default:            return "Ke zpracování";
        }
    }
}
