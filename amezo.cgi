#!/usr/bin/perl
use strict;
use warnings;
use Encode ();
use Fcntl qw(:flock O_RDWR O_CREAT O_EXCL);
use FindBin qw($Bin);
chdir($Bin);   # 相対パスで動くので、カレントをスクリプトのあるディレクトリに固定する

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
my $copyright = <<EOL;
<!-- 
     Script for amezo-like BBS
     Copyright (C) 1999-2003 amezo_
     http://www17.big.or.jp/~amezo_/
     http://ame.x0.com/
-->
EOL

my $amezo   = '＠あめぞう';
my $urlbase = 'http://ame.x0.com/';
my $admin   = 'サポート';

# 同じ板への連続投稿の最短間隔(秒)。この間隔未満の投稿はエラーにして保存しない。
# 0 にすると間隔制限なし(リロードの index 再生成も毎回行う)。
my $post_interval = 5;

# スレッド削除機能の合言葉ハッシュ($6$…=SHA-512 crypt)を置くファイル。
# このファイルが無い/空なら削除機能は誰も使えない(初期状態)。
# .htaccess で web からは読めないようにしてある。
# 設定方法は README.txt の「スレッドの削除」を参照。
my $delcryptfile = 'delpass.txt';

# サブルーチンと共有する状態(use strict ではここで宣言しておく必要がある)
my ($folder, $res, $name, $mail, $comm, $subj) = ('') x 6;
my %form;
my $page = '';

# ---------------------------------------------------------------------------
# GET なら自分自身のソースを返して終了
# ---------------------------------------------------------------------------
my $cgi = (($ENV{'SCRIPT_FILENAME'} // '') =~ m{/([^/]+)$}) ? $1 : 'amezo.cgi';
if(($ENV{'REQUEST_METHOD'} // '') eq 'GET'){
	print "Content-type: text/plain; charset=UTF-8\n\n";
	if(open(my $src, '<', "./$cgi")){
		print $_ while <$src>;
		close($src);
	}
	exit;
}

# ---------------------------------------------------------------------------
# 入力の受け取りと検証
# ---------------------------------------------------------------------------
my $content_len = $ENV{'CONTENT_LENGTH'} || 0;
($content_len =~ /^\d+$/ && $content_len <= 7500) || error('投稿内容が大きすぎます');
my $buffer = '';
read(STDIN, $buffer, $content_len);
length($buffer) > 7500 && error('投稿内容が大きすぎます');

my $referer = $ENV{'HTTP_REFERER'} // '';
$referer =~ s/%([a-fA-F0-9][a-fA-F0-9])/pack("C", hex($1))/eg;
my $urlbase_cmp = $urlbase;
$urlbase_cmp =~ s{^(https?://)www\.}{$1};   # 設定側の www. も外して比較する
$referer =~ s{^(https?://)www\.}{$1};       # www. 有りでアクセスされても通す
$referer =~ /^\Q$urlbase_cmp\E([\w\.\-]+)/ || error('エラー');
$folder = $1;
my $origin = $ENV{'HTTP_ORIGIN'} // '';
$origin =~ s{//www\.}{//};
$origin ne '' && index($urlbase_cmp, "$origin/") != 0 && error('不正なリクエストです');

# ---------------------------------------------------------------------------
# フォームの分解
# ---------------------------------------------------------------------------
foreach my $pair (split(/&/, $buffer)) {
	my ($key, $value) = split(/=/, $pair, 2);
	next unless defined $key;
	$value = '' unless defined $value;
	$value =~ tr/+/ /;
	$value =~ s/%([a-fA-F0-9][a-fA-F0-9])/pack("C", hex($1))/eg;
	$value = to_utf8($value);
	$value = strip_invisible($value);
	$value =~ s/&/&amp;/g;
	$value =~ s/\"/&quot;/g;
	$value =~ s/</&lt;/g;
	$value =~ s/>/&gt;/g;
	$value =~ s/'/&#39;/g;
	$value =~ s/\r\n/\r/g;
	$value =~ s/\n/\r/g;
	$value =~ s/\r/<br>/g if $key eq 'comm';
	$value =~ s/[\x00-\x1f]//g;
	$form{$key} = $value;
}
$form{$_} = '' foreach grep { !defined $form{$_} } qw(name mail comm subj folder res sub from next);

$name = $form{'name'};
$mail = $form{'mail'};
$comm = $form{'comm'};
$subj = $form{'subj'};
$folder = $form{'folder'} if length($form{'folder'});
error('板名が不正です') if $folder eq '' || $folder =~ m{/|\.\.} || !is_board($folder);
$res = $form{'res'};
$res =~ /^\d*$/ || error('不正なスレッド指定です');
res() if length($form{'sub'});

my $next = $form{'next'};
$next = 1 unless $next =~ /^\d{1,6}$/ && $next > 0;
$next += 20;
$page = ($next != 21) ? '2' : '';

my $reload = 0;
$reload = 1 if $name eq $subj && $name eq $comm;
$reload = 1 unless length($name) || length($subj) || length($comm);
my @br = ($comm =~ /<br>/g);
(@br + 0 > 20 || clen($subj) > 20) && error("コメントが長すぎます");
$name =~ s/ |　|\xE2\x80\x8D//g;
$name = ccut($name, 30);
$comm =~ s/&gt;(&gt;)+/&gt;/g;
$subj =~ s/ |　|＿//g;

# ---------------------------------------------------------------------------
# NGワード
# ---------------------------------------------------------------------------
my $comm2 = $comm;
$comm2 =~ s/%([a-fA-F0-9][a-fA-F0-9])/pack("C", hex($1))/eg;
if(open(my $ngfh, '<', './ng.txt')){   # ng.txt が無ければ NGワード処理は省略
	while(my $line = <$ngfh>){
		$line =~ s/\r?\n\z//;               # CRLF の ng.txt でも動くように
		next unless length $line;           # 空行は無視(空パターンは直前のパターンを再利用してしまう)
		my ($ng, $opt) = split(/,/, $line);
		next unless defined $ng && length $ng;
		$opt = '' unless defined $opt;
		$ng = quotemeta($ng);               # 記号を無効化して正規表現に埋め込む
		if($opt eq 'n'){
			$reload = 1 if $name =~ /$ng/;
		}elsif($opt eq 'c'){
			$reload = 1 if $comm2 =~ /$ng/;
		}else{
			$name =~ s/$ng//g; $comm =~ s/$ng//g; $mail =~ s/$ng//g; $subj =~ s/$ng//g;
		}
	}
	close($ngfh);
}

# ---------------------------------------------------------------------------
# 投稿の保存
# ---------------------------------------------------------------------------
if($next == 21 && !$reload){

	my $admin_re = quotemeta($admin);
	$name =~ s/$admin_re/＃$admin/g;

	my $delcrypt = load_delcrypt();
	$delcrypt ne '' && crypt($name, $delcrypt) eq $delcrypt && del();
	$subj = '' if length($res);
	length($name) || error("投稿者を記入してください");
	length($comm) || error("コメントが入力されていません");
	length($res) || length($subj) || error("題名が入力されていません");
	if(my $left = post_interval_left()){
		error("連投を検知しました。あと $left 秒ほど待ってから投稿してください");
	}
	check() if length($subj);

	$comm =~ s/(https?\:[\w\.\~\-\/\?\+\=\:\@\%\;\#\&]+)/url($1)/eg;
	length($mail) && ($name = "<a href=\"mailto:$mail \">$name </a>");

	my ($sec, $min, $hour, $mday, $mon, $year, $wday) = localtime(time);
	my $yy    = sprintf('%02d', $year % 100);
	my $month = sprintf('%02d', $mon + 1);
	$mday = sprintf('%02d', $mday);
	$hour = sprintf('%02d', $hour);
	$min  = sprintf('%02d', $min);
	$sec  = sprintf('%02d', $sec);
	my $wd = ("日", "月", "火", "水", "木", "金", "土")[$wday];
	my $date = "20${yy}年${month}月${mday}日(${wd})${hour}時${min}分${sec}秒";
	$res = "$yy$month$mday$hour$min$sec" unless length($res);
	exit if $res =~ /\D/;

	my ($w, $file);
	if(length($subj)){
		# 新規スレッド: ID(秒単位の日時)が使用済みなら 1 つ進めて空きを探す
		for(my $try = 0; ; $try++){
			$file = "./$folder/$res.html";
			last if sysopen($w, $file, O_RDWR|O_CREAT|O_EXCL, 0644);
			error('スレッドを作成できません.') if !$!{EEXIST} || $try >= 30;
			$res++;
		}
	}else{
		$file = "./$folder/$res.html";
		open($w, '+<', $file) || error('スレッドがありません.');
	}
	flock($w, LOCK_EX);

	my ($cnt, $pos, $prev) = (0, 0, '');
	while(my $l = <$w>){
		last unless $l =~ /<dt>(\d+)/;
		$cnt  = $1;
		$pos  = tell($w);
		$prev = $l;
	}
	seek($w, $pos, 0);
	$cnt++;

	if($prev =~ /<b>(.+) <\/b>.+<dd>(.+) <\/dl>/ && $name eq $1 && $comm eq $2){
		error('二重カキコです.');
	}
	my ($subj1, $subj2) = ('', '');
	if(length($subj)){
		$subj1 = "<meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>$subj </title>";
		$subj2 = "<font size=+2 color=red><b>$subj </b></font>";
	}
	my $line = <<EOL;
${subj1}<dl><dt>${cnt}${subj2}投稿者：<font color=forestgreen><b>$name </b></font>
<font size=-1>　投稿日：$date</font><br><dd>$comm </dl>
EOL
	$line =~ s/\n//g;
	print $w "$line\n";
	$line = <<EOL;
<form method=post action="../$cgi">
<input type=hidden name="res" value="$res">
投稿者 <input type=text name="name" size=20>
メール <input type=text name="mail" size=20><br>
<input type=submit value="↑へのレスカキコ" ><br>
<textarea name="comm" rows=4 cols=70 ></textarea>
</form>
EOL
	$line =~ s/\n//g;
	print $w "$line\n";
	flock($w, LOCK_UN);
	close($w);
	touch_lasttime();

}

# ---------------------------------------------------------------------------
# 板の設定を読む
# ---------------------------------------------------------------------------
my ($color, $title) = ('', '');
if(open(my $bl, '<', './blist.txt')){
	while(my $l = <$bl>){
		$l =~ s/\r?\n\z//;
		my ($fol, $c, $t) = split(/,/, $l);
		next unless defined $fol;
		($color, $title) = (defined $c ? $c : '', defined $t ? $t : '');
		last if $fol eq $folder;
	}
	close($bl);
}

my $index      = "index$page.html";
my $index_file = "./$folder/$index";
my $main = ($folder eq 'main') ? "(メイン)" : '';
my $bg;
($color, $bg) = split(/!/, $color);
$color = '' unless defined $color;
$bg = (defined $bg && length $bg) ? " background=\"$bg\"" : '';
my $text = '';
if($color =~ /\*$/){
	$text = q( text="#ffffff" link="red" vlink="orange");
	chop $color;
}
$title =~ s/#c#/,/g;
my $title0 = $title;
if($title0 =~ /alt=\"([^\"]+)/){
	$title0 = $1;
	$amezo = '';
}

if($next == 21 && $reload && $post_interval > 0){
	# リロード連打対策: 直近に index を作っていたら作り直さない(投稿は対象外)
	my $mt = (stat($index_file))[9] || 0;
	redirect() if time() - $mt < $post_interval;
}

# ---------------------------------------------------------------------------
# index(2).html の再生成
# ---------------------------------------------------------------------------
open(my $w, '+<', $index_file) || redirect();
flock($w, LOCK_EX|LOCK_NB) || redirect();

print $w <<EOF;
<html><head><meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title0}${amezo}${main}</title></head>
$copyright
<body$bg bgcolor="$color"$text>
<font size=+2>${title}${amezo}${main}</font>
EOF

if(open(my $hd, '<', './header.html')){
	print $w $_ while <$hd>;
	close($hd);
}

print $w <<EOF;
<form method=post action="../$cgi">
<input type=submit value="次のページ">
<input type=text name="next" value="$next" size="3">〜</form>
<font size=2>
<!-- HEAD LINE -->
EOF

my @dir;
if(opendir(my $dh, "./$folder")){
	@dir = readdir($dh);
	closedir($dh);
}

for(my $i = 0; $i < @dir; $i++){
	my $ts = ($dir[$i] =~ /^\d+\.html/) ?
		sprintf('%011d', (stat("./$folder/$dir[$i]"))[9] || 0) : ' ';
	$dir[$i] = "$ts,$dir[$i]";
}
@dir = sort { $b cmp $a } @dir;

# ヘッドライン(題名の一覧)
for(my $i = $next - 21; $i < $next + 100 - 21 && $i < @dir; $i++){
	my ($ts, $file) = split(/,/, $dir[$i]);
	last if $ts eq ' ';
	my $first = '';
	if(open(my $r, '<', "./$folder/$file")){
		$first = <$r>;
		close($r);
		$first = '' unless defined $first;
	}
	my $t = ($first =~ /<b>([^\<]*)<\/b>/) ? $1 : '';
	my $j = $i + 1;
	print $w " $j<a href=\"$file\">$t</a>\n";
}
print $w "<!-- HEAD LINE END -->\n</font>\n";

# スレッド本体(1行目 + 最後の7行)
for(my $i = $next - 21; $i < $next - 1 && $i < @dir; $i++){
	my ($ts, $file) = split(/,/, $dir[$i]);
	last if $ts eq ' ';
	print $w <<EOL;
<table border=1 cellspacing=1 cellpadding=2 width=100% bgcolor="#efefef"><tr><td><font color="#000000">
EOL
	my @lines;
	my $j = 0;
	if(open(my $r, '<', "./$folder/$file")){
		my $first = <$r>;
		if(defined $first){
			$first =~ s/<meta[^>]*>//g;
			$first =~ s/<title>.*<\/title>//;
			print $w $first;
		}
		while(defined(my $l = <$r>)){
			last if $l =~ /^<form/;
			$lines[$j % 7] = $l;
			$j++;
		}
		close($r);
	}
	my $k = $j - 7;
	$k = 0 if $k < 0;
	for(my $m = $k; $m < $j; $m++){
		print $w $lines[$m % 7];
	}
	my $tid = ($file =~ /(.+)\.html/) ? $1 : '';
	my $sub_html = '';
	if($j > 200){
		my $from = $j - 98;
		$sub_html = "<input type=text name=\"from\" value=\"$from\" size=\"4\">\n"
		          . "<input type=submit name=\"sub\" value=\"〜\">　\n";
	}
	print $w <<EOL;
</font></td></tr></table>
<form method=post action="../$cgi">
<input type=hidden name="res" value="$tid">
投稿者 <input type=text name="name" size=20>
メール <input type=text name="mail" size=20><br>
<input type=submit value="↑へのレスカキコ" >
<a href="$tid.html">レス全部を見る</a>
${sub_html}<a href="#top">上へ　</a><a href="./">リロード</a><br>
<textarea name="comm" rows=4 cols=70 ></textarea>
</form><hr>
EOL

}

print $w <<EOF;
<form method=post action="../$cgi">
<input type=submit value="次のページ">
<input type=text name="next" value="$next" size="3">〜</form>
<hr></body></html>
EOF

truncate($w, tell($w));
flock($w, LOCK_UN);
close($w);
redirect();

# ---------------------------------------------------------------------------
# サブルーチン
# ---------------------------------------------------------------------------

sub redirect {
	my $target = $page ? $index : '';
	print "Location: $urlbase$folder/$target\n\n\n";
	exit;
}

sub url {
	my ($dsp) = @_;
	my $url = $dsp;
	$url =~ s/&amp;/&/g;
	return "<a href=\"$url\" target=\"_blank\" rel=\"noopener noreferrer nofollow\">$dsp</a>";
}

sub error {
	my ($msg) = @_;
	print "Content-type: text/html; charset=UTF-8\n\n<html><head>"
		. '<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">'
		. "</head><body><h2>$msg</h2></body></html>";
	exit;
}

sub res {
	my $from = $form{'from'};
	$from = 1 unless $from =~ /^\d+$/;
	open(my $r, '<', "./$folder/$res.html") || error('スレッドがありません.');
	print "Content-type: text/html; charset=UTF-8\n\n";
	my $first = <$r>;
	print $first if defined $first;
	my $hit;
	while(defined(my $l = <$r>)){
		if($l =~ /<dt>(\d+)/ && $1 >= $from){
			$hit = $l;
			last;
		}
	}
	print $hit if defined $hit;
	my $fol = "<input type=hidden name=\"folder\" value=\"$folder\">";
	while(my $l = <$r>){
		if($l =~ /<\/form>/){
			$l =~ s/(action=\")\.\.\//$1/;
			$l =~ s/(<\/form>)/$fol$1/;
		}
		print $l;
	}
	exit;
}

sub del {
	if(length($mail)){
		$name = $admin;
		$mail = '' unless $mail =~ /\@/;
		return;
	}
	print "Content-type: text/html\n\n";
	exit unless length($res);
	my $file = "./$folder/$res.html";
	if(!length($comm)){
		my $newfile = "./$folder/x$res.html";
		rename($file, $newfile);
		chmod 0600, $newfile;
		exit;
	}
	my $dels = ',' . $comm . ',';
	$dels =~ s/(\d+)\-(\d+)/join(',',($1..$2))/eg;
	$dels =~ s/<br>/,/g;
	my $ts = (stat($file))[9];
	my @lines;
	if(open(my $r, '<', $file)){
		@lines = <$r>;
		close($r);
	}
	my ($year, $mon, $mday, $hour, $min, $sec);
	open(my $w, '+>', $file) || exit;
	flock($w, LOCK_EX);
	foreach my $l (@lines){
		if($l =~ /<dt>(\d+)/){
			my $n = ",$1,";
			next if index($dels, $n) >= 0;
		}
		($year,$mon,$mday,$hour,$min,$sec) = ($1,$2,$3,$4,$5,$6)
			if $l =~ /(\d\d\d\d).{3}(\d\d).{3}(\d\d).{3}\(.{3}\)(\d\d).{3}(\d\d).{3}(\d\d)/;
		print $w $l;
	}
	close($w);
	# 残ったレスの最後の日時から更新時刻を手計算で復元する(日付が拾えなければ元のまま)
	if(defined $year){
		$year -= 1900;
		$mon--;
		my $uru = int(($year - 72) / 4);
		if(((($year + 1900) % 4) == 0) && ($mon < 2)){ $uru--; }
		$ts = $year - 70;
		$ts = $ts * 365 + (0,31,59,90,120,151,181,212,243,273,304,334)[$mon] + $mday + $uru;
		$ts = $ts * 24 + $hour - 9;
		$ts = $ts * 60 + $min;
		$ts = $ts * 60 + $sec;
		$ts -= $1*24*60*60 if $dels =~ /p(\d+)/;
	}
	utime $ts+1, $ts+1, $file;
	chmod 0404, $file if $dels =~ /x/;
	exit;
}

sub check {
	my $ip = $ENV{'REMOTE_ADDR'} // '';
	my $time = time();
	my %iplist;
	if(open(my $z, '<', 'global.mem')){
		while(my $l = <$z>){
			chomp $l;
			my ($ip_o, $time_o) = split(' ', $l);
			next unless defined $ip_o && defined $time_o && $time_o =~ /^\d+$/;
			$iplist{$ip_o} = $time_o if $time - $time_o < 180;
		}
		close($z);
	}
	if($iplist{$ip}){
		my $remain = 180 - ($time - $iplist{$ip});
		error("あと " . $remain . "秒たってから投稿してください");
	}
	$iplist{$ip} = $time;
	if(open(my $z, '>', 'global.mem')){
		for my $k (keys %iplist){
			print $z "$k $iplist{$k}\n";
		}
		close($z);
	}
	chmod 0600, "global.mem";
}

# ---------------------------------------------------------------------------
# UTF-8 版で追加したヘルパ
# ---------------------------------------------------------------------------

# 注意: Encode::decode は CHECK を渡すと第2引数を「消費」して空にしてしまう。
#       元の値を壊さないよう、必ずコピーを渡すこと。
sub decode_bytes {
	my ($enc, $str) = @_;
	my $src = $str;
	my $dec;
	return $dec if eval { $dec = Encode::decode($enc, $src, Encode::FB_CROAK()); 1 };
	return undef;
}

# 受け取ったバイト列を UTF-8 に揃える。
# 妥当な UTF-8 ならそのまま、そうでなければ CP932(Shift_JIS)とみなして変換する。
sub to_utf8 {
	my ($str) = @_;
	return '' unless defined $str;
	my $dec = decode_bytes('UTF-8', $str);
	$dec = decode_bytes('cp932', $str) unless defined $dec;
	return Encode::encode('UTF-8', $dec) if defined $dec;
	(my $out = $str) =~ s/[\x80-\xff]//g;
	return $out;
}

# 文字数を返す(バイト数ではなく)。
sub clen {
	my ($str) = @_;
	return 0 unless defined $str;
	my $dec = decode_bytes('UTF-8', $str);
	return defined $dec ? length($dec) : length($str);
}

# 先頭から指定文字数で切り詰める。多バイト文字を途中で割らない。
sub ccut {
	my ($str, $max) = @_;
	return '' unless defined $str;
	my $dec = decode_bytes('UTF-8', $str);
	return substr($str, 0, $max) unless defined $dec;
	return Encode::encode('UTF-8', substr($dec, 0, $max));
}

# 削除機能の合言葉ハッシュを別ファイルから読む。
# ファイルが無い/空なら空文字を返し、削除機能は無効になる。
sub load_delcrypt {
	local $/;
	open(my $f, '<', $delcryptfile) or return '';
	my $c = <$f>;
	close($f);
	return '' unless defined $c;
	$c =~ s/^\s+//;
	$c =~ s/\s+$//;
	return $c;
}

# ---------------------------------------------------------------------------
# パッチで追加したヘルパ
# ---------------------------------------------------------------------------

# 板名が blist.txt に載っているか(ホワイトリスト)。
sub is_board {
	my ($f) = @_;
	open(my $bf, '<', './blist.txt') or return 0;
	while(my $l = <$bf>){
		$l =~ s/\r?\n\z//;
		my ($n) = split(/,/, $l);
		if(defined $n && $n eq $f){ close($bf); return 1; }
	}
	close($bf);
	return 0;
}

# 見えない文字(ゼロ幅・双方向制御・C1制御など)を除く。管理人名の偽装対策。
# ZWJ(U+200D)は絵文字の連結に使うので残す(名前欄だけ別途除去している)。
sub strip_invisible {
	my ($str) = @_;
	my $dec = decode_bytes('UTF-8', $str);
	return $str unless defined $dec;
	$dec =~ s/[\x{0080}-\x{009F}\x{00AD}\x{034F}\x{061C}\x{115F}\x{1160}\x{17B4}\x{17B5}\x{180B}-\x{180E}\x{200B}\x{200C}\x{200E}\x{200F}\x{2028}-\x{202E}\x{2060}-\x{206F}\x{3164}\x{FEFF}\x{FFA0}\x{FFF9}-\x{FFFB}]//g;
	return Encode::encode('UTF-8', $dec);
}

# 前回の投稿から $post_interval 秒経っていなければ残り秒数を返す(0 なら投稿可)。
sub post_interval_left {
	return 0 unless $post_interval > 0;
	my $last = 0;
	if(open(my $k, '<', "./$folder/lasttime.txt")){
		$last = <$k>;
		close($k);
	}
	$last = 0 unless defined $last && $last =~ /^\d+$/;
	my $left = $post_interval - (time() - $last);
	return $left > 0 ? $left : 0;
}

# 投稿を保存した時刻を板ごとに記録する。
sub touch_lasttime {
	return unless $post_interval > 0;
	open(my $k, '>', "./$folder/lasttime.txt") or return;
	print {$k} time();
	close($k);
}