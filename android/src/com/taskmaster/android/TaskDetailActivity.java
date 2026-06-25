package com.taskmaster.android;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.view.*;
import android.webkit.WebView;
import android.widget.*;
import com.taskmaster.android.model.TaskNode;
import com.taskmaster.android.util.MarkdownRenderer;
import com.taskmaster.android.util.TaskRepository;
import com.taskmaster.android.util.YamlParser;

import java.io.File;

public class TaskDetailActivity extends Activity {
    private TaskNode task;
    private String folderPath;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_task_detail);
        folderPath = getIntent().getStringExtra("folderPath");
        if (folderPath == null) { finish(); return; }

        Toolbar toolbar = (Toolbar) findViewById(R.id.toolbar);
        setActionBar(toolbar);
        getActionBar().setDisplayHomeAsUpEnabled(true);
    }

    @Override
    protected void onResume() {
        super.onResume();
        loadTask();
    }

    private void loadTask() {
        File folder   = new File(folderPath);
        String name   = folder.getName();
        File yamlFile = new File(folder, name + ".yaml");
        if (!yamlFile.exists()) { finish(); return; }

        String yamlText = TaskRepository.readFile(yamlFile);
        if (yamlText == null) { finish(); return; }

        YamlParser meta = YamlParser.parse(yamlText);
        task = new TaskNode();
        task.id = meta.id; task.title = meta.title; task.status = meta.status;
        task.priority = meta.priority; task.category = meta.category; task.tags = meta.tags;
        task.created = meta.created; task.modified = meta.modified;
        task.order = meta.order; task.flag = meta.flag; task.folderPath = folderPath;

        File mdFile = new File(folder, name + ".md");
        String body = mdFile.exists() ? TaskRepository.readFile(mdFile) : "";
        task.body = body != null ? body : "";

        renderUi();
    }

    private void renderUi() {
        getActionBar().setTitle(task.title);

        TextView statusView = (TextView) findViewById(R.id.statusView);
        statusView.setText(task.statusLabel());
        statusView.setBackgroundColor(statusColor(task.status));
        statusView.setTextColor(Color.WHITE);

        ((TextView) findViewById(R.id.priorityView)).setText("Priorita: " + task.priority);

        final Button flagBtn = (Button) findViewById(R.id.flagBtn);
        flagBtn.setText(task.flag ? "Odznacit" : "Oznacit");
        flagBtn.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                task.flag = !task.flag;
                TaskRepository.saveMeta(task);
                renderUi();
            }
        });

        final Button doneBtn = (Button) findViewById(R.id.doneBtn);
        doneBtn.setText(task.isDone() ? "Znovu otevrit" : "Hotovo");
        doneBtn.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                task.status = task.isDone() ? "todo" : "done";
                TaskRepository.saveMeta(task);
                renderUi();
            }
        });

        ((Button) findViewById(R.id.prioUpBtn)).setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                if (task.priority < 10) { task.priority++; TaskRepository.saveMeta(task); renderUi(); }
            }
        });
        ((Button) findViewById(R.id.prioDownBtn)).setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                if (task.priority > 1) { task.priority--; TaskRepository.saveMeta(task); renderUi(); }
            }
        });

        StringBuilder sb = new StringBuilder();
        if (!task.category.isEmpty()) sb.append(task.category);
        for (String tag : task.tags) sb.append("  #").append(tag);
        TextView catView = (TextView) findViewById(R.id.categoryView);
        String catStr = sb.toString().trim();
        catView.setText(catStr);
        catView.setVisibility(catStr.isEmpty() ? View.GONE : View.VISIBLE);

        String dates = "";
        if (!task.created.isEmpty())  dates  = "Vytvoreno: "  + task.created .substring(0, Math.min(16, task.created .length())).replace("T"," ");
        if (!task.modified.isEmpty()) dates += "   Zmeneno: " + task.modified.substring(0, Math.min(16, task.modified.length())).replace("T"," ");
        ((TextView) findViewById(R.id.datesView)).setText(dates);

        WebView webView = (WebView) findViewById(R.id.bodyWebView);
        String html = task.body.trim().isEmpty()
            ? "<html><body style='font-family:sans-serif;color:#999;padding:12px;'>Zadny obsah</body></html>"
            : MarkdownRenderer.toHtml(task.body);
        webView.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null);

        ((Button) findViewById(R.id.editBtn)).setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                Intent i = new Intent(TaskDetailActivity.this, EditTaskActivity.class);
                i.putExtra("folderPath", folderPath);
                i.putExtra("isNew", false);
                startActivity(i);
            }
        });

        ((Button) findViewById(R.id.addChildBtn)).setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                Intent i = new Intent(TaskDetailActivity.this, EditTaskActivity.class);
                i.putExtra("parentPath", folderPath);
                i.putExtra("isNew", true);
                i.putExtra("inheritStatus", task.status);
                i.putExtra("inheritPriority", task.priority);
                i.putExtra("inheritCategory", task.category);
                startActivity(i);
            }
        });
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        if (item.getItemId() == android.R.id.home) { finish(); return true; }
        return super.onOptionsItemSelected(item);
    }

    private int statusColor(String s) {
        switch (s) {
            case "in_progress": return Color.parseColor("#1565C0");
            case "blocked":     return Color.parseColor("#B71C1C");
            case "done":        return Color.parseColor("#2E7D32");
            default:            return Color.parseColor("#757575");
        }
    }
}
