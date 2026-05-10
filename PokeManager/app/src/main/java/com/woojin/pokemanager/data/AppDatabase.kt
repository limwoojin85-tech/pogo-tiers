package com.woojin.pokemanager.data

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(entities = [MyPokemon::class], version = 2)
abstract class AppDatabase : RoomDatabase() {
    abstract fun pokemonDao(): PokemonDao

    companion object {
        @Volatile private var INSTANCE: AppDatabase? = null

        fun get(context: Context): AppDatabase =
            INSTANCE ?: synchronized(this) {
                Room.databaseBuilder(context.applicationContext, AppDatabase::class.java, "pokemanager.db")
                    // v1 → v2: profile 컬럼 추가. 기존 데이터 보존 위해 fallback (drop) 대신 destructive migration off
                    .fallbackToDestructiveMigration()
                    .build().also { INSTANCE = it }
            }
    }
}
